"""MCP JSON-RPC resources/list + resources/read (B33/B36)."""
from __future__ import annotations

from threadforge.mcp_server import handle_message, parse_job_resource, resource_uri


def test_parse_job_resource():
    jid, kind = parse_job_resource("threadforge://job/job-abc/pcf")
    assert jid == "job-abc" and kind == "pcf"
    assert resource_uri("job-abc", "pcf") == "threadforge://job/job-abc/pcf"


def test_handle_tools_and_unknown():
    listed = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "ingest_dexpi" in names
    unknown = handle_message({"jsonrpc": "2.0", "id": 2, "method": "nope"})
    assert unknown["error"]["code"] == -32601
    called = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ingest_dexpi", "arguments": {"path": "sample_pid.xml"}},
        }
    )
    assert "error" not in called


def test_resources_list_empty_or_populated(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_DATA", str(tmp_path))
    monkeypatch.delenv("TF_API_TOKENS", raising=False)
    from threadforge.server import create_app

    create_app()
    msg = handle_message({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    assert "resources" in msg["result"]
    missing = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "threadforge://job/missing/pcf"},
        }
    )
    assert missing["error"]["code"] == -32000
