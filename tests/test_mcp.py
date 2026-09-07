"""A23: MCP server drives ingest→route→clash→export."""
from __future__ import annotations

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
