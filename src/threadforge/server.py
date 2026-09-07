"""FastAPI OpenAPI + SQLite artefact registry + bearer auth + jobs.

Offline/deterministic: no network calls inside tool handlers.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from threadforge import agent_tools
from threadforge.generators import default_output_dir

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError("pip install 'threadforge[server]'") from exc


SCHEMA_VERSION = 1
_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


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


def init_registry(db_path: Optional[Path] = None) -> Path:
    path = db_path or registry_db_path()
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artefacts (
            job_id TEXT,
            kind TEXT,
            path TEXT,
            sha256 TEXT,
            dirty INTEGER DEFAULT 0,
            meta TEXT,
            PRIMARY KEY (job_id, kind, path)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    conn.close()
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
    db = init_registry(db_path)
    digest = file_sha256(path) if path.exists() else ""
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT OR REPLACE INTO artefacts(job_id, kind, path, sha256, dirty, meta) VALUES (?,?,?,?,?,?)",
        (job_id, kind, str(path), digest, 1 if dirty else 0, json.dumps(meta or {})),
    )
    conn.commit()
    conn.close()
    return digest


def list_artefact_hashes(job_id: str, db_path: Optional[Path] = None) -> dict[str, str]:
    db = init_registry(db_path)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT path, sha256 FROM artefacts WHERE job_id=?", (job_id,)
    ).fetchall()
    conn.close()
    return {path: sha for path, sha in rows}


def _parse_tokens() -> dict[str, dict[str, str]]:
    """TF_API_TOKENS=engineer:eng-token:write,reviewer:rev-token:read"""
    raw = os.environ.get("TF_API_TOKENS", "")
    out: dict[str, dict[str, str]] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) >= 3:
            role, token, access = bits[0], bits[1], bits[2]
            out[token] = {"role": role, "access": access}
    return out


class Principal(BaseModel):
    role: str
    access: str
    token: str


def require_auth(authorization: Optional[str] = Header(default=None)) -> Principal:
    tokens = _parse_tokens()
    if not tokens:
        # auth disabled when no tokens configured (dev)
        return Principal(role="engineer", access="write", token="")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    info = tokens.get(token)
    if not info:
        raise HTTPException(status_code=401, detail="invalid token")
    return Principal(role=info["role"], access=info["access"], token=token)


def require_write(principal: Principal = Depends(require_auth)) -> Principal:
    if principal.access != "write":
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
    with _JOBS_LOCK:
        _JOBS[job_id]["state"] = "running"
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
        # register hashes
        hashes = {}
        for p in out.rglob("*"):
            if p.is_file():
                digest = register_artefact(job_id, p.suffix or "file", p, db_path=registry_db_path())
                hashes[str(p)] = digest
        with _JOBS_LOCK:
            _JOBS[job_id]["state"] = "done"
            _JOBS[job_id]["artefacts"] = hashes
            _JOBS[job_id]["result"] = result
    except Exception as exc:  # noqa: BLE001
        with _JOBS_LOCK:
            _JOBS[job_id]["state"] = "error"
            _JOBS[job_id]["error"] = str(exc)


def create_app() -> FastAPI:
    app = FastAPI(title="ThreadForge", version="1.0.0", description="Piping digital thread tools")
    init_registry()

    @app.get("/health")
    def health() -> dict[str, Any]:
        dd = data_dir()
        writable = os.access(dd, os.W_OK)
        db = registry_db_path()
        init_registry(db)
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        conn.close()
        schema_ok = row is not None and int(row[0]) == SCHEMA_VERSION
        # fixture shas
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
        if principal.access == "read" and name in {
            "revise_pid",
            "cascade_rerun",
            "export_artefacts",
            "run_pipeline_stage",
        }:
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
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
                        digest = register_artefact("local", fp.suffix or "file", fp)
                        try:
                            hashes[str(fp.relative_to(out))] = digest
                        except ValueError:
                            hashes[str(fp)] = digest
            result = dict(result)
            result.setdefault("artefact_hashes", hashes)
        return result

    @app.post("/jobs", status_code=202)
    def create_job(body: JobCreate, _auth: Principal = Depends(require_write)) -> dict[str, str]:
        with _JOBS_LOCK:
            if body.job_key:
                for existing in _JOBS.values():
                    if existing.get("job_key") == body.job_key:
                        raise HTTPException(
                            status_code=409,
                            detail=f"duplicate job_key: {body.job_key}",
                        )
            job_id = f"job-{uuid.uuid4().hex[:10]}"
            _JOBS[job_id] = {"state": "queued", "id": job_id, "job_key": body.job_key}
        _EXECUTOR.submit(_run_job, job_id, body.fixture, body.path, body.schedule)
        return {"id": job_id, "job_id": job_id, "status": "queued"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, _auth: Principal = Depends(require_auth)) -> dict[str, Any]:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "ok": False})

    return app


def export_openapi(path: Optional[Path] = None) -> Path:
    app = create_app()
    out = path or Path(__file__).resolve().parents[2] / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    return out
