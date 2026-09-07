"""A23: MCP server drives ingest→route→clash→export."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from threadforge.mcp_server import call_tool, list_tools


def test_mcp_tool_list_and_pipeline(tmp_path):
    names = {t["name"] for t in list_tools()}
    assert "ingest_dexpi" in names
    assert "export_artefacts" in names
    call_tool("ingest_dexpi", {})
    call_tool("export_artefacts", {"output_dir": str(tmp_path)})
    # clash via agent tool if present
    if "query_graph" in names:
        call_tool("query_graph", {"summary": True})


def _hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for fp in root.rglob("*"):
        if fp.is_file() and fp.name != "registry.db":
            out[str(fp.relative_to(root))] = hashlib.sha256(fp.read_bytes()).hexdigest()
    return out


def test_mcp_http_export_hash_parity(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from threadforge import agent_tools
    from threadforge.server import create_app

    mcp_dir = tmp_path / "mcp"
    http_dir = tmp_path / "http"
    mcp_dir.mkdir()
    http_dir.mkdir()

    call_tool("ingest_dexpi", {"path": "sample_pid_rich.xml"})
    call_tool("export_artefacts", {"output_dir": str(mcp_dir)})
    mcp_hashes = _hashes(mcp_dir)

    agent_tools.SESSION.graph = None
    agent_tools.SESSION.job = None
    agent_tools.SESSION.cascade = None
    agent_tools.SESSION.schedule = None
    monkeypatch.setenv("TF_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("TF_API_TOKENS", raising=False)
    client = TestClient(create_app())
    assert client.post("/tools/ingest_dexpi", json={"path": "sample_pid_rich.xml"}).status_code == 200
    exported = client.post("/tools/export_artefacts", json={"output_dir": str(http_dir)})
    assert exported.status_code == 200
    http_hashes = exported.json().get("artefact_hashes") or _hashes(http_dir)
    common = set(mcp_hashes) & set(http_hashes)
    assert common
    for key in common:
        assert mcp_hashes[key] == http_hashes[key], key
