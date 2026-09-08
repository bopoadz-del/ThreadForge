"""SQLite + Postgres registry via Alembic (B29) + hashed keys / audit (B30).

Schema is applied only through Alembic revisions. Both backends must land on
``SCHEMA_REVISION`` with the same table set. Audit rows are append-only
(triggers abort UPDATE/DELETE).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_REVISION = "0001_m5"
SCHEMA_VERSION = 2
REQUIRED_TABLES = (
    "schema_meta",
    "artefacts",
    "api_keys",
    "audit_events",
    "jobs",
    "job_events",
)
ROLES = ("admin", "engineer", "reviewer")
KEY_HASH_PREFIX = "tfk1"
_EPHEMERAL_LOCK = threading.Lock()
_EPHEMERAL: dict[str, Any] = {}


def alembic_ini() -> Path:
    return ROOT / "alembic.ini"


def database_url_from_env(default_sqlite: Optional[Path] = None) -> str:
    raw = os.environ.get("TF_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if raw:
        return raw
    path = default_sqlite or (Path(os.environ.get("TF_DATA", ".")) / "registry.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_url(path)


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def hash_api_key(token: str, salt: str) -> str:
    """PBKDF2-HMAC-SHA256 — stored value is never the bearer secret."""
    dk = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{KEY_HASH_PREFIX}${salt}${dk.hex()}"


def new_key_hash(token: str) -> str:
    salt = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    return hash_api_key(token, salt)


def verify_api_key(token: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != KEY_HASH_PREFIX:
        return False
    return hmac.compare_digest(hash_api_key(token, parts[1]), stored)


def _alembic_config(url: str) -> Any:
    from alembic.config import Config

    cfg = Config(str(alembic_ini()))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def apply_migrations(url: str) -> dict[str, Any]:
    """Alembic upgrade heads. Returns measured revision + tables."""
    from alembic import command

    command.upgrade(_alembic_config(url), "head")
    return inspect_schema(url)


def inspect_schema(url: str) -> dict[str, Any]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if url.startswith("sqlite"):
                rows = conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname='public' ORDER BY tablename"
                    )
                ).fetchall()
            tables = [str(r[0]) for r in rows]
            ver = conn.execute(
                text("SELECT value FROM schema_meta WHERE key='schema_version'")
            ).scalar()
    finally:
        engine.dispose()
    return {
        "revision": str(rev or ""),
        "schema_version": int(ver) if ver is not None else None,
        "tables": tables,
        "url_kind": "postgresql" if url.startswith("postgres") else "sqlite",
    }


def find_pg_bin() -> Optional[Path]:
    for cand in (
        Path("/usr/lib/postgresql/16/bin"),
        Path("/usr/lib/postgresql/15/bin"),
        Path("/usr/pgsql-16/bin"),
        Path("/usr/bin"),
    ):
        if (cand / "initdb").is_file() and (cand / "pg_ctl").is_file():
            return cand
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb and pg_ctl:
        return Path(initdb).parent
    return None


def start_ephemeral_postgres() -> str:
    """initdb + pg_ctl on a private data dir. Measured live server, not a mock."""
    with _EPHEMERAL_LOCK:
        existing = _EPHEMERAL.get("url")
        if existing:
            return str(existing)
        bindir = find_pg_bin()
        if bindir is None:
            raise RuntimeError("postgres binaries missing (initdb/pg_ctl)")
        root = Path(os.environ.get("TF_PGDATA", str(Path.home() / "tf-pg-ephemeral-m5")))
        data = root / "data"
        sock = root / "sock"
        if root.exists():
            subprocess.run(
                [str(bindir / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        sock.mkdir(exist_ok=True)
        log = root / "pg.log"
        port = int(os.environ.get("TF_PGPORT", "55433"))
        subprocess.run(
            [str(bindir / "initdb"), "-D", str(data), "--auth=trust", "--no-sync", "-U", "tf"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(bindir / "pg_ctl"),
                "-D",
                str(data),
                "-o",
                f"-p {port} -k {sock}",
                "-l",
                str(log),
                "start",
            ],
            check=True,
        )
        time.sleep(0.3)
        subprocess.run(
            [str(bindir / "createdb"), "-h", str(sock), "-p", str(port), "-U", "tf", "threadforge"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"postgresql+psycopg://tf@/threadforge?host={sock}&port={port}"
        _EPHEMERAL["url"] = url
        _EPHEMERAL["data"] = data
        _EPHEMERAL["bindir"] = bindir
        return url


def stop_ephemeral_postgres() -> None:
    with _EPHEMERAL_LOCK:
        data = _EPHEMERAL.get("data")
        bindir = _EPHEMERAL.get("bindir")
        if not data or not bindir:
            return
        subprocess.run(
            [str(bindir / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _EPHEMERAL.clear()


def migrate_both(sqlite_path: Path) -> dict[str, Any]:
    """Apply the same Alembic head to SQLite and Postgres. Measured."""
    sqlite = apply_migrations(sqlite_url(sqlite_path))
    pg_url = (
        os.environ.get("TF_POSTGRES_URL")
        or os.environ.get("TF_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not pg_url or not str(pg_url).startswith("postgres"):
        pg_url = start_ephemeral_postgres()
    postgres = apply_migrations(pg_url)
    return {"sqlite": sqlite, "postgres": postgres}


def connect(url: str) -> Engine:
    return create_engine(url, future=True)


def seed_hashed_keys(url: str, tokens: list[tuple[str, str, str]]) -> list[str]:
    """Insert (role, access, plaintext) as hashes. Returns stored hashes."""
    stored: list[str] = []
    engine = connect(url)
    try:
        with engine.begin() as conn:
            for role, access, token in tokens:
                h = new_key_hash(token)
                conn.execute(
                    text(
                        "INSERT INTO api_keys(role, access, key_hash) VALUES (:r, :a, :h)"
                    ),
                    {"r": role, "a": access, "h": h},
                )
                stored.append(h)
    finally:
        engine.dispose()
    return stored


def lookup_principal(url: str, token: str) -> Optional[dict[str, str]]:
    engine = connect(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT role, access, key_hash FROM api_keys")).fetchall()
    finally:
        engine.dispose()
    for role, access, stored in rows:
        if verify_api_key(token, str(stored)):
            return {"role": str(role), "access": str(access)}
    return None


def append_audit(
    url: str,
    role: str,
    action: str,
    resource: str,
    payload: Optional[dict[str, Any]] = None,
) -> int:
    engine = connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events(ts, role, action, resource, payload) "
                    "VALUES (:ts, :role, :action, :resource, :payload)"
                ),
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "role": role,
                    "action": action,
                    "resource": resource,
                    "payload": json.dumps(payload or {}, sort_keys=True),
                },
            )
            n = conn.execute(text("SELECT COUNT(*) FROM audit_events")).scalar()
    finally:
        engine.dispose()
    return int(n or 0)


def audit_mutation_blocked(url: str) -> dict[str, bool]:
    """UPDATE and DELETE on audit_events must raise (append-only)."""
    engine = connect(url)
    blocked = {"update": False, "delete": False}
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events(ts, role, action, resource, payload) "
                    "VALUES ('t', 'admin', 'probe', 'audit', '{}')"
                )
            )
        for kind, sql in (
            ("update", "UPDATE audit_events SET action='mutated' WHERE action='probe'"),
            ("delete", "DELETE FROM audit_events WHERE action='probe'"),
        ):
            try:
                with engine.begin() as conn:
                    conn.execute(text(sql))
            except Exception:  # noqa: BLE001
                blocked[kind] = True
    finally:
        engine.dispose()
    return blocked


def put_job(url: str, job_id: str, state: str, job_key: Optional[str] = None, extra: Optional[dict[str, Any]] = None) -> None:
    engine = connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO jobs(id, state, job_key, extra) VALUES (:id, :state, :job_key, :extra) "
                    "ON CONFLICT(id) DO UPDATE SET state=:state, extra=:extra"
                ),
                {
                    "id": job_id,
                    "state": state,
                    "job_key": job_key,
                    "extra": json.dumps(extra or {}, sort_keys=True),
                },
            )
    finally:
        engine.dispose()


def get_job(url: str, job_id: str) -> Optional[dict[str, Any]]:
    engine = connect(url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, state, job_key, extra FROM jobs WHERE id=:id"),
                {"id": job_id},
            ).fetchone()
    finally:
        engine.dispose()
    if not row:
        return None
    extra = json.loads(row[3] or "{}")
    return {"id": row[0], "state": row[1], "job_key": row[2], **extra}


def find_job_by_key(url: str, job_key: str) -> Optional[str]:
    engine = connect(url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM jobs WHERE job_key=:k"), {"k": job_key}
            ).fetchone()
    finally:
        engine.dispose()
    return str(row[0]) if row else None


def append_job_event(url: str, job_id: str, name: str, data: Optional[dict[str, Any]] = None) -> int:
    engine = connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO job_events(job_id, name, payload) VALUES (:j, :n, :p)"
                ),
                {"j": job_id, "n": name, "p": json.dumps(data or {}, sort_keys=True)},
            )
            eid = conn.execute(text("SELECT MAX(id) FROM job_events WHERE job_id=:j"), {"j": job_id}).scalar()
    finally:
        engine.dispose()
    return int(eid or 0)


def list_job_events(url: str, job_id: str, after: int = 0) -> list[dict[str, Any]]:
    engine = connect(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, name, payload FROM job_events "
                    "WHERE job_id=:j AND id>:a ORDER BY id"
                ),
                {"j": job_id, "a": after},
            ).fetchall()
    finally:
        engine.dispose()
    out: list[dict[str, Any]] = []
    for eid, name, payload in rows:
        body = json.loads(payload or "{}")
        out.append({"id": int(eid), "name": str(name), "data": body})
    return out


def register_artefact_row(
    url: str,
    job_id: str,
    kind: str,
    path: Path,
) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    engine = connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO artefacts(job_id, kind, path, sha256, dirty, meta) "
                    "VALUES (:j, :k, :p, :s, 0, '{}') "
                    "ON CONFLICT(job_id, kind, path) DO UPDATE SET sha256=:s, dirty=0"
                ),
                {"j": job_id, "k": kind, "p": str(path), "s": digest},
            )
    finally:
        engine.dispose()
    return digest


def artefact_payload(url: str, job_id: str, kind: str) -> Optional[tuple[bytes, str, str]]:
    """Canonical bytes + sha256 + media type for one kind."""
    engine = connect(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT path, sha256 FROM artefacts WHERE job_id=:j AND kind=:k ORDER BY path"
                ),
                {"j": job_id, "k": kind},
            ).fetchall()
    finally:
        engine.dispose()
    if not rows:
        return None
    if len(rows) == 1:
        path = Path(str(rows[0][0]))
        if not path.is_file():
            return None
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        return data, digest, "application/octet-stream"
    files = {Path(str(p)).name: s for p, s in rows}
    data = json.dumps({"kind": kind, "files": files}, sort_keys=True, indent=2).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    return data, digest, "application/json"


def infer_kind(path: Path) -> str:
    parent = path.parent.name.lower()
    mapping = {
        "pcf": "pcf",
        "iso": "isometric",
        "ga": "ga",
        "qty": "quantities",
        "csv": "csv",
        "dlb": "dlb",
        "supports": "supports",
        "routes": "routes",
        "clash": "clash",
        "ifc": "ifc",
        "dxf": "dxf",
        "xlsx": "xlsx",
        "pdf": "pdf",
        "system": "system",
        "test_pack": "test_pack",
        "test_packs": "test_pack",
        "wp": "work_package",
        "work_packages": "work_package",
    }
    if parent in mapping:
        return mapping[parent]
    suf = path.suffix.lower()
    return {
        ".pcf": "pcf",
        ".svg": "isometric",
        ".ifc": "ifc",
        ".dxf": "dxf",
        ".csv": "csv",
        ".xlsx": "xlsx",
        ".pdf": "pdf",
        ".json": parent or "json",
    }.get(suf, parent or "file")


def sqlite_connect_raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))
