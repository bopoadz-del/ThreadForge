"""Agent tool registry + call_tool dispatch."""

from threadforge.agent_tools import call_tool, list_tools


def test_tool_registry_includes_new_tools():
    names = list_tools()
    assert "export_artefacts" in names
    assert "dexpi_coverage" in names
    assert "look_ahead" in names


def test_call_tool_ingest_and_coverage(tmp_path):
    r = call_tool("ingest_dexpi", {})
    assert r["ok"] is True
    cov = call_tool("dexpi_coverage", {})
    assert "gaps" in cov
    # export into tmp
    from threadforge import agent_tools

    agent_tools.SESSION.output_dir = tmp_path
    exported = call_tool("export_artefacts", {"output_dir": str(tmp_path)})
    assert exported["ok"] is True
    assert (tmp_path / "ga" / "plot_plan.svg").exists()
