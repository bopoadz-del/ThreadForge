"""FastAPI OpenAPI + Alembic registry + RBAC + SSE + artefact ETag.

Offline/deterministic: no network calls inside tool handlers.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterator, Optional

from threadforge import agent_tools
from threadforge.generators import default_output_dir
from threadforge.guards import (
    GuardError,
    check_upload_size,
    rate_limit_hit,
    reject_xml_bomb,
)
from threadforge.persist import (
    ROLES,
    SCHEMA_VERSION,
    append_audit,
    append_job_event,
    apply_migrations,
    artefact_payload,
    find_job_by_key,
    get_job,
    infer_kind,
    list_job_events,
    lookup_principal,
    put_job,
    register_artefact_row,
    seed_hashed_keys,
    sqlite_url,
)

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError("pip install 'threadforge[server]'") from exc


_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_URL_LOCK = threading.Lock()
_APP_URL: dict[str, str] = {}


def data_dir() -> Path:
    raw = os.environ.get("TF_DATA")
    if raw:
        p = Path(raw)
    else:
        p = default_output_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def registry_db_path(output_dir: Optional[Path] = None) -> Path:
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        return out / "registry.db"
    return data_dir() / "registry.db"


def current_db_url() -> str:
    with _URL_LOCK:
        if "url" in _APP_URL:
            return _APP_URL["url"]
    env = os.environ.get("TF_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env:
        return env
    return sqlite_url(registry_db_path())


def init_registry(db_path: Optional[Path] = None) -> Path:
    """Alembic-migrate the SQLite registry (or TF_DATABASE_URL)."""
    if os.environ.get("TF_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        url = current_db_url()
        apply_migrations(url)
        with _URL_LOCK:
            _APP_URL["url"] = url
        return registry_db_path()
    path = db_path or registry_db_path()
    url = sqlite_url(path)
    apply_migrations(url)
    with _URL_LOCK:
        _APP_URL["url"] = url
    return path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def register_artefact(
    job_id: str,
    kind: str,
    path: Path,
    dirty: bool = False,
    meta: Optional[dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> str:
    if db_path is not None:
        init_registry(db_path)
    return register_artefact_row(current_db_url(), job_id, kind, path)


def list_artefact_hashes(job_id: str, db_path: Optional[Path] = None) -> dict[str, str]:
    if db_path is not None:
        init_registry(db_path)
    from sqlalchemy import create_engine, text

    engine = create_engine(current_db_url())
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT path, sha256 FROM artefacts WHERE job_id=:j"),
                {"j": job_id},
            ).fetchall()
    finally:
        engine.dispose()
    return {str(path): str(sha) for path, sha in rows}


def _parse_tokens() -> dict[str, dict[str, str]]:
    """TF_API_TOKENS=engineer:eng-token:write,reviewer:rev-token:read[,admin:adm-token:admin]."""
    raw = os.environ.get("TF_API_TOKENS", "")
    out: dict[str, dict[str, str]] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) >= 3:
            role, token, access = bits[0], bits[1], bits[2]
            if role not in ROLES:
                if access == "admin":
                    role = "admin"
                elif access == "write":
                    role = "engineer"
                else:
                    role = "reviewer"
            out[token] = {"role": role, "access": access}
    return out


def _seed_tokens_if_needed() -> None:
    tokens = _parse_tokens()
    if not tokens:
        return
    url = current_db_url()
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM api_keys")).scalar()
    finally:
        engine.dispose()
    if int(n or 0) > 0:
        return
    seed_hashed_keys(
        url,
        [(info["role"], info["access"], token) for token, info in tokens.items()],
    )


class Principal(BaseModel):
    role: str
    access: str
    token: str


def require_auth(authorization: Optional[str] = Header(default=None)) -> Principal:
    tokens = _parse_tokens()
    if not tokens:
        return Principal(role="engineer", access="write", token="")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    hashed = lookup_principal(current_db_url(), token)
    if hashed:
        return Principal(role=hashed["role"], access=hashed["access"], token=token)
    info = tokens.get(token)
    if not info:
        raise HTTPException(status_code=401, detail="invalid token")
    return Principal(role=info["role"], access=info["access"], token=token)


def require_write(principal: Principal = Depends(require_auth)) -> Principal:
    if principal.access != "write" and principal.role not in {"admin", "engineer"}:
        raise HTTPException(status_code=403, detail="write role required")
    if principal.role == "reviewer":
        raise HTTPException(status_code=403, detail="write role required")
    return principal


class ToolCall(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class JobCreate(BaseModel):
    fixture: Optional[str] = None
    path: Optional[str] = None
    schedule: Optional[str] = None
    job_key: Optional[str] = None


def _run_job(job_id: str, fixture: Optional[str], path: Optional[str], schedule: Optional[str]) -> None:
    url = current_db_url()
    put_job(url, job_id, "running")
    append_job_event(url, job_id, "running", {})
    try:
        out = data_dir() / "jobs" / job_id
        out.mkdir(parents=True, exist_ok=True)
        if path:
            agent_tools.ingest_dexpi(path=path)
        elif fixture:
            agent_tools.ingest_dexpi(path=fixture)
        else:
            agent_tools.ingest_dexpi()
        if schedule:
            agent_tools.attach_schedule(path=schedule)
        result = agent_tools.export_artefacts(output_dir=str(out))
        hashes: dict[str, str] = {}
        for p in out.rglob("*"):
            if p.is_file() and p.name != "registry.db":
                kind = infer_kind(p)
                digest = register_artefact_row(url, job_id, kind, p)
                hashes[str(p)] = digest
        put_job(url, job_id, "done", extra={"artefacts": hashes, "result": result})
        append_job_event(url, job_id, "done", {"n": len(hashes)})
    except Exception as exc:  # noqa: BLE001
        put_job(url, job_id, "error", extra={"error": str(exc)})
        append_job_event(url, job_id, "error", {"error": str(exc)})


def _rate_key(request: Request, principal: Optional[Principal]) -> str:
    if principal and principal.token:
        return f"tok:{principal.token}"
    client = request.client.host if request.client else "local"
    return f"ip:{client}"


def create_app() -> FastAPI:
    app = FastAPI(title="ThreadForge", version="2.0.0", description="Piping digital thread tools")
    init_registry()
    _seed_tokens_if_needed()

    @app.middleware("http")
    async def upload_and_rate(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        cl = request.headers.get("content-length")
        if cl and cl.isdigit():
            try:
                check_upload_size(int(cl))
            except GuardError as exc:
                return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code})
        limited = path.rstrip("/") in {"/tools", "/upload"} or (
            path.rstrip("/") == "/jobs" and request.method == "POST"
        )
        if limited:
            key = request.headers.get("authorization") or (
                request.client.host if request.client else "anon"
            )
            if rate_limit_hit(key):
                return JSONResponse(status_code=429, content={"detail": "rate limit", "code": "rate_limit"})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, Any]:
        dd = data_dir()
        writable = os.access(dd, os.W_OK)
        init_registry()
        from sqlalchemy import create_engine, text

        engine = create_engine(current_db_url())
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value FROM schema_meta WHERE key='schema_version'")
                ).fetchone()
        finally:
            engine.dispose()
        schema_ok = row is not None and int(row[0]) == SCHEMA_VERSION
        manifest = Path(__file__).resolve().parents[2] / "fixtures" / "public" / "dexpi13" / "fetch_manifest.json"
        fixture_shas = manifest.is_file()
        status = "ok" if writable and schema_ok and fixture_shas else "degraded"
        return {
            "status": status,
            "fail_closed": True,
            "data_dir_writable": writable,
            "registry_schema": "head" if schema_ok else "missing",
            "fixture_shas": fixture_shas,
            "schema_version": SCHEMA_VERSION,
        }

    @app.get("/tools")
    def tools(_auth: Principal = Depends(require_auth)) -> list[str]:
        return sorted(agent_tools.TOOL_REGISTRY.keys())

    @app.post("/tools/{name}")
    async def call_tool(
        name: str,
        request: Request,
        principal: Principal = Depends(require_auth),
    ) -> Any:
        if name not in agent_tools.TOOL_REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
        if principal.role == "reviewer" or (
            principal.access == "read"
            and name
            in {
                "revise_pid",
                "cascade_rerun",
                "export_artefacts",
                "run_pipeline_stage",
            }
        ):
            raise HTTPException(status_code=403, detail="read-only token")
        try:
            raw = await request.json()
        except Exception:
            raw = {}
        if isinstance(raw, dict) and isinstance(raw.get("arguments"), dict):
            args = raw["arguments"]
        elif isinstance(raw, dict):
            args = raw
        else:
            args = {}
        fn = agent_tools.TOOL_REGISTRY[name]
        try:
            result = fn(**args)
        except TypeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GuardError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        append_audit(current_db_url(), principal.role, f"tool:{name}", name, {"ok": True})
        if name == "export_artefacts" and isinstance(result, dict):
            out = Path(
                args.get("output_dir")
                or getattr(agent_tools.SESSION, "output_dir", None)
                or default_output_dir()
            )
            hashes: dict[str, str] = {}
            if out.exists():
                for fp in out.rglob("*"):
                    if fp.is_file() and fp.name != "registry.db":
                        digest = register_artefact("local", infer_kind(fp), fp)
                        try:
                            hashes[str(fp.relative_to(out))] = digest
                        except ValueError:
                            hashes[str(fp)] = digest
            result = dict(result)
            result.setdefault("artefact_hashes", hashes)
        return result

    @app.post("/jobs", status_code=202)
    def create_job(body: JobCreate, principal: Principal = Depends(require_write)) -> dict[str, str]:
        url = current_db_url()
        if body.job_key:
            existing = find_job_by_key(url, body.job_key)
            if existing:
                raise HTTPException(status_code=409, detail=f"duplicate job_key: {body.job_key}")
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        put_job(url, job_id, "queued", job_key=body.job_key)
        append_job_event(url, job_id, "queued", {})
        append_audit(url, principal.role, "job.create", job_id, {"job_key": body.job_key})
        _EXECUTOR.submit(_run_job, job_id, body.fixture, body.path, body.schedule)
        return {"id": job_id, "job_id": job_id, "status": "queued"}

    @app.get("/jobs/{job_id}")
    def get_job_http(job_id: str, _auth: Principal = Depends(require_auth)) -> dict[str, Any]:
        job = get_job(current_db_url(), job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/jobs/{job_id}/artefacts/{kind}")
    def get_artefact(
        job_id: str,
        kind: str,
        request: Request,
        _auth: Principal = Depends(require_auth),
    ) -> Response:
        payload = artefact_payload(current_db_url(), job_id, kind)
        if payload is None:
            raise HTTPException(status_code=404, detail="artefact not found")
        data, digest, media = payload
        etag = f'"{digest}"'
        inm = request.headers.get("if-none-match")
        if inm:
            want = inm.strip()
            if want == etag or want.strip('"') == digest:
                return Response(status_code=304, headers={"ETag": etag})
        return Response(content=data, media_type=media, headers={"ETag": etag, "X-Content-SHA256": digest})

    @app.get("/jobs/{job_id}/events")
    def job_events_sse(job_id: str, _auth: Principal = Depends(require_auth)) -> StreamingResponse:
        url = current_db_url()
        if get_job(url, job_id) is None:
            raise HTTPException(status_code=404, detail="job not found")

        def gen() -> Iterator[str]:
            last = 0
            for _ in range(400):
                rows = list_job_events(url, job_id, after=last)
                for ev in rows:
                    last = int(ev["id"])
                    yield f"event: {ev['name']}\ndata: {json.dumps(ev, sort_keys=True)}\n\n"
                    if ev["name"] in {"done", "error"}:
                        return
                time.sleep(0.05)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/upload")
    async def upload_xml(
        request: Request,
        principal: Principal = Depends(require_write),
    ) -> dict[str, Any]:
        data = await request.body()
        try:
            check_upload_size(len(data))
            reject_xml_bomb(data)
        except GuardError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        dest = data_dir() / "uploads" / f"{uuid.uuid4().hex}.xml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        append_audit(current_db_url(), principal.role, "upload", str(dest), {"n": len(data)})
        return {"path": str(dest), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "ok": False})

    @app.exception_handler(GuardError)
    async def guard_exc_handler(request: Request, exc: GuardError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code, "ok": False})

    return app


def export_openapi(path: Optional[Path] = None) -> Path:
    app = create_app()
    out = path or Path(__file__).resolve().parents[2] / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    return out
