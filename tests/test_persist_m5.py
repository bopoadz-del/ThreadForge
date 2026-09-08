"""B29–B35: Alembic dual-backend, RBAC, ETag, SSE, MCP, guards, determinism."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from threadforge.guards import MAX_UPLOAD_BYTES, GuardError, reject_xml_bomb, reset_rate_limits
from threadforge.persist import (
    REQUIRED_TABLES,
    ROLES,
    SCHEMA_REVISION,
    SCHEMA_VERSION,
    audit_mutation_blocked,
    hash_api_key,
    migrate_both,
    new_key_hash,
    verify_api_key,
)

ROOT = Path(__file__).resolve().parents[1]


def test_key_hash_is_not_plaintext():
    token = "eng-token"
    stored = new_key_hash(token)
    assert token not in stored
    assert stored.startswith("tfk1$")
    assert verify_api_key(token, stored)
    assert not verify_api_key("wrong", stored)
    salt = stored.split("$")[1]
    assert hash_api_key(token, salt) == stored


def test_alembic_sqlite_and_postgres(tmp_path):
    both = migrate_both(tmp_path / "reg.db")
    for side in ("sqlite", "postgres"):
        info = both[side]
        assert info["revision"] == SCHEMA_REVISION
        assert info["schema_version"] == SCHEMA_VERSION
        for table in REQUIRED_TABLES:
            assert table in info["tables"], (side, table)
    assert set(REQUIRED_TABLES) <= set(both["sqlite"]["tables"])
    assert set(REQUIRED_TABLES) <= set(both["postgres"]["tables"])


def test_audit_append_only_both(tmp_path):
    migrate_both(tmp_path / "reg2.db")
    from threadforge.persist import sqlite_url

    sqlite_blocked = audit_mutation_blocked(sqlite_url(tmp_path / "reg2.db"))
    assert sqlite_blocked["update"] is True
    assert sqlite_blocked["delete"] is True
    pg_url = os.environ.get("TF_POSTGRES_URL") or os.environ.get("TF_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not pg_url or not str(pg_url).startswith("postgres"):
        from threadforge.persist import start_ephemeral_postgres

        pg_url = start_ephemeral_postgres()
    pg_blocked = audit_mutation_blocked(pg_url)
    assert pg_blocked["update"] is True
    assert pg_blocked["delete"] is True


def test_xml_bomb_rejected():
    bomb = (
        b'<?xml version="1.0"?>\n<!DOCTYPE lolz [\n'
        b'<!ENTITY lol "lol">\n<!ENTITY lol2 "&lol;&lol;">\n]>\n<lolz>&lol2;</lolz>'
    )
    with pytest.raises(GuardError) as exc:
        reject_xml_bomb(bomb)
    assert exc.value.code == "xml_bomb"
    assert exc.value.status == 400


def test_upload_too_large():
    with pytest.raises(GuardError) as exc:
        reject_xml_bomb(b"x" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.status == 413


def _client(tmp_path, monkeypatch, tokens="admin:adm-token:admin,engineer:eng-token:write,reviewer:rev-token:read"):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from threadforge.server import create_app

    reset_rate_limits()
    monkeypatch.setenv("TF_DATA", str(tmp_path))
    monkeypatch.setenv("TF_API_TOKENS", tokens)
    monkeypatch.delenv("TF_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app())


def test_rbac_three_roles(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    rev = client.post("/jobs", headers={"Authorization": "Bearer rev-token"}, json={"fixture": "sample_pid.xml"})
    assert rev.status_code == 403
    eng = client.post("/jobs", headers={"Authorization": "Bearer eng-token"}, json={"fixture": "sample_pid.xml"})
    assert eng.status_code == 202
    adm = client.get("/tools", headers={"Authorization": "Bearer adm-token"})
    assert adm.status_code == 200
    from sqlalchemy import create_engine, text

    from threadforge.server import current_db_url

    engine = create_engine(current_db_url())
    with engine.connect() as conn:
        hashes = [r[0] for r in conn.execute(text("SELECT key_hash FROM api_keys")).fetchall()]
        roles = {r[0] for r in conn.execute(text("SELECT role FROM api_keys")).fetchall()}
        n_audit = conn.execute(text("SELECT COUNT(*) FROM audit_events")).scalar()
    engine.dispose()
    assert roles == set(ROLES) or roles >= {"admin", "engineer", "reviewer"}
    for h in hashes:
        assert "eng-token" not in h and "rev-token" not in h and "adm-token" not in h
    assert int(n_audit or 0) >= 1


def _wait_job(client, job_id: str, headers: dict[str, str], timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        body = r.json()
        if body.get("state") in {"done", "error"}:
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} not finished")


def test_artefact_etag_304(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer eng-token"}
    created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid_rich.xml"})
    assert created.status_code == 202
    job_id = created.json()["id"]
    job = _wait_job(client, job_id, headers)
    assert job["state"] == "done"
    first = client.get(f"/jobs/{job_id}/artefacts/pcf", headers=headers)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    digest = first.headers.get("x-content-sha256")
    assert etag and digest
    assert digest == etag.strip('"')
    second = client.get(
        f"/jobs/{job_id}/artefacts/pcf",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == 304


def test_sse_job_events(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer eng-token"}
    created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid.xml"})
    job_id = created.json()["id"]
    with client.stream("GET", f"/jobs/{job_id}/events", headers=headers) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())
    assert "event: queued" in text
    assert "event: running" in text or "event: done" in text
    assert "event: done" in text or "event: error" in text


def test_mcp_resource_hash_equals_http(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer eng-token"}
    created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid_rich.xml"})
    job_id = created.json()["id"]
    _wait_job(client, job_id, headers)
    http = client.get(f"/jobs/{job_id}/artefacts/pcf", headers=headers)
    assert http.status_code == 200
    http_sha = http.headers["x-content-sha256"]
    from threadforge.mcp_server import read_resource, resource_uri

    mcp = read_resource(resource_uri(job_id, "pcf"))
    assert mcp["sha256"] == http_sha
    assert mcp["blob"] == http.content


def test_rate_limit_429(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": "Bearer eng-token"}
    codes = [client.get("/tools", headers=headers).status_code for _ in range(25)]
    assert 429 in codes
    assert 200 in codes


def test_cross_process_hashes(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    script = ROOT / "scripts" / "cross_process_export.py"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r1 = subprocess.run(
        [sys.executable, str(script), str(a)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    r2 = subprocess.run(
        [sys.executable, str(script), str(b)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    h1 = json.loads(r1.stdout.strip().splitlines()[-1])
    h2 = json.loads(r2.stdout.strip().splitlines()[-1])
    common = set(h1) & set(h2)
    assert common
    mismatches = [k for k in common if h1[k] != h2[k]]
    assert not mismatches
