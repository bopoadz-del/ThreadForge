"""Richer DEXPI fixture + coverage report."""

from threadforge.ingest_dexpi import coverage_report, load_fixture


def test_rich_fixture_counts():
    g = load_fixture("sample_pid_rich.xml")
    s = g.connectivity_summary()
    assert s["sheet_count"] == 3
    assert s["equipment_count"] >= 4
    assert s["pipeline_count"] >= 4
    assert s["battery_limit_count"] >= 3
    assert s["volume_count"] >= 4
    assert len(g.instruments) >= 5
    # ProcessInstrumentFunction / InstrumentationFunction ingested
    assert "210-PT-201" in g.instruments
    assert "210-TT-201" in g.instruments
    # PipingNetworkSegment
    assert "LINE-200-P-1001" in g.pipelines
    assert g.pipelines["LINE-200-P-1001"].metadata.get("element") == "PipingNetworkSegment"
    # Nozzle XYZ
    nz = g.nozzles["200-V-101-N1"]
    assert nz.x == 15.0
    assert nz.z == 18.0
    assert g.metadata.get("multi_sheet") is True


def test_coverage_report_lists_gaps():
    cov = coverage_report()
    assert "Equipment" in cov["supported_elements"]
    assert "ProcessInstrumentFunction" in cov["supported_elements"]
    assert len(cov["gaps"]) >= 5
    assert "WALL" in cov["wall"] or "wall" in cov["wall"].lower() or "XSD" in cov["wall"]


def test_lite_fixture_still_works():
    g = load_fixture("sample_pid.xml")
    assert g.connectivity_summary()["sheet_count"] == 2
