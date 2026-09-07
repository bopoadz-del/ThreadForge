"""Smoke tests for agent tool surface."""


from threadforge import agent_tools


def test_tool_registry():
    expected = {
        "ingest_dexpi",
        "query_graph",
        "revise_pid",
        "cascade_rerun",
        "build_test_packs",
        "build_work_packages",
        "attach_schedule",
        "look_ahead",
        "co_activity_check",
        "maturity_check",
        "run_pipeline_stage",
        "export_artefacts",
        "dexpi_coverage",
    }
    assert expected.issubset(set(agent_tools.list_tools()))


def test_pipeline_run_all(fixtures_dir):
    agent_tools.ingest_dexpi()
    out = agent_tools.run_pipeline_stage("outputs", run_all=True)
    assert out["ok"] is True
    assert out["stages"]["outputs"] == "done"
    agent_tools.build_work_packages()
    agent_tools.attach_schedule(fixtures_dir / "sample_schedule.json")
    co = agent_tools.co_activity_check()
    assert "flagged_count" in co
