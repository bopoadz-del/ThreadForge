"""D2: no silent fabricated geometry — flags + maturity refuse."""

from __future__ import annotations

from threadforge.generators import (
    _iso_svg,
    generate_dlb,
    generate_isometric,
    generate_quantities,
    write_pcf_text,
)
from threadforge.ingest_dexpi import load_fixture
from threadforge.maturity import MaturityLevel, maturity_check
from threadforge.pcf_reader import parse_pcf
from threadforge.routing import route_pipeline


def test_lite_has_one_fabricated_line():
    g = load_fixture("sample_pid.xml")
    flags = {
        p.line_number: route_pipeline(g, p).get("geometry_source")
        for p in g.pipelines.values()
    }
    fabricated = [ln for ln, src in flags.items() if src == "fabricated"]
    real = [ln for ln, src in flags.items() if src == "nozzle_xyz"]
    assert fabricated == ["120-P-1002"]
    assert "120-P-1001" in real
    assert "124-LPWP-2505" in real


def test_rich_fixture_zero_fabricated():
    g = load_fixture("sample_pid_rich.xml")
    for p in g.pipelines.values():
        r = route_pipeline(g, p)
        assert r.get("geometry_source") == "nozzle_xyz", p.line_number
        assert r.get("status") == "ok"


def test_artefacts_carry_fabricated_flag():
    g = load_fixture("sample_pid.xml")
    qty = generate_quantities(g)
    row = next(r for r in qty.payload["rows"] if r["line_number"] == "120-P-1002")
    assert row["length_source"] == "fabricated"
    assert row["geometry_source"] == "fabricated"
    assert row["status"] == "degraded"

    lid = "LINE-120-P-1002"
    iso = generate_isometric(g, lid)
    assert iso.payload["geometry_source"] == "fabricated"
    assert iso.payload["status"] == "degraded"
    r = route_pipeline(g, g.pipelines[lid])
    svg = _iso_svg(r, "120-P-1002 [FABRICATED GEOMETRY]")
    assert "FABRICATED" in svg

    pcf = write_pcf_text(g, lid)
    doc = parse_pcf(pcf)
    assert any("FABRICATED" in v.upper() for v in doc.attributes.values())

    dlb = generate_dlb(g)
    assert "120-P-1002" in dlb.payload["fabricated_lines"]


def test_maturity_refuses_pcf_export_when_fabricated():
    g = load_fixture("sample_pid.xml")
    check = maturity_check(MaturityLevel.IFC, MaturityLevel.IFC, action="pcf_export", graph=g)
    assert check["allowed"] is False
    assert "120-P-1002" in check["fabricated_lines"]
    assert "Refused" in check["message"]


def test_maturity_allows_when_no_fabricated():
    g = load_fixture("sample_pid_rich.xml")
    check = maturity_check(MaturityLevel.IFC, MaturityLevel.IFC, action="ifc_export", graph=g)
    assert check["fabricated_lines"] == []
    assert check["allowed"] is True
