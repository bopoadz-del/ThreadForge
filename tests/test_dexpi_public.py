"""E3: real public DEXPI fixtures + GenericAttribute mapping."""

from __future__ import annotations

import hashlib
from pathlib import Path

from threadforge.ingest_dexpi import (
    DEXPI_COVERAGE_GAPS,
    coverage_report,
    load_fixture,
    validate_xsd,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "fixtures" / "public"
DEXPI13 = PUBLIC / "dexpi13"

PINNED_C01 = {"pipelines": 23, "equipment": 21, "nozzles": 21, "instruments": 6}
PINNED_GAP_COUNT = 6

C01_SHA = "a2b172f04e0dcf9a668e158c6dee3b5fd0dd4e9027b572dc39e54470562b809c"
XSD_SHA = "f14652c0f3ff79eea6bb1c92f276c79f41ebad2945324f70b348c377c00385ff"


def test_vendored_c01_sha256():
    path = DEXPI13 / "pids" / "C01V04-VER.EX01.xml"
    assert path.is_file()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == C01_SHA
    assert path.stat().st_size == 445726


def test_vendored_xsd_4_1_sha256():
    path = DEXPI13 / "xsd" / "ProteusPIDSchema_4.1.xsd"
    assert path.is_file()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == XSD_SHA
    assert path.stat().st_size == 92156
    # 4.1.1 RC1 also vendored when fetch succeeded
    rc = DEXPI13 / "xsd" / "ProteusPIDSchema_4.1.1_RC1.xsd"
    assert rc.is_file()


def test_c01_pinned_counts_and_generic_attributes():
    g = load_fixture("C01V04-VER.EX01.xml")
    assert len(g.pipelines) == PINNED_C01["pipelines"]
    assert len(g.equipment) == PINNED_C01["equipment"]
    assert len(g.nozzles) == PINNED_C01["nozzles"]
    assert len(g.instruments) == PINNED_C01["instruments"]
    # LineNumberAssignmentClass mapped (not raw element IDs)
    numbers = {p.line_number for p in g.pipelines.values()}
    assert any(n.isdigit() for n in numbers), numbers
    assert not any(n.startswith("PipingNetworkSegment-") for n in numbers)
    # DN → bore, PipingClass, FluidCode present
    sample = next(iter(g.pipelines.values()))
    assert sample.nominal_bore and "80" in sample.nominal_bore
    assert sample.metadata.get("PipingClass")
    assert sample.metadata.get("FluidCode")
    # Equipment TagNameAssignmentClass (e.g. H1007 / P4711 / T4750)
    eq_tags = {e.tag for e in g.equipment.values()}
    assert {"H1007", "P4711", "T4750"} <= eq_tags or {"H1007", "P4711"} <= eq_tags
    # Nozzles parented to equipment (ShapeCatalogue orphans allowed)
    parented = [n for n in g.nozzles.values() if n.equipment_id in g.equipment]
    assert len(parented) >= 19


def test_p02_opc_cross_sheet_joins():
    """C08 has no XML upstream; P02 covers OPC cross-sheet Connection joins."""
    g = load_fixture("P02V01-VER.EX01.xml")
    assert any(t.metadata.get("role") == "off_page_connector" for t in g.tags.values()) or any(
        "OffPage" in (t.engineering.component_class or "") for t in g.tags.values()
    )
    joins = [
        e
        for e in g.from_tos.values()
        if "OffPage" in e.from_id or "OffPage" in e.to_id or e.connection_type == "connection"
    ]
    assert joins, "expected OPC/Connection join on P02"
    assert any(e.matched for e in joins)


def test_c03_e06_p01_loadable():
    for name in ("C03V04-VER.EX02.xml", "E06V01-VER.EX01.xml", "P01V01-VER.EX01.xml"):
        g = load_fixture(name)
        assert len(g.pipelines) + len(g.equipment) + len(g.nozzles) > 0


def test_coverage_gaps_shrunk_and_pinned():
    cov = coverage_report()
    assert "GenericAttributes" in cov["supported_elements"]
    assert "PipeOffPageConnector" in cov["supported_elements"]
    assert len(DEXPI_COVERAGE_GAPS) == cov["gap_count"]
    assert cov["gap_count"] == PINNED_GAP_COUNT
    assert "vendor" in cov["wall"].lower() or "Vendor" in cov["wall"]


def test_validate_xsd_with_vendored_schema():
    """Product path: C01 SchemaVersion 4.1.1 → RC1 XSD via xmlschema → validated."""
    path = DEXPI13 / "pids" / "C01V04-VER.EX01.xml"
    result = validate_xsd(path)
    assert result["status"] == "validated"
    assert result["ok"] is True
    assert result.get("engine") == "xmlschema"
    assert "4.1.1" in Path(result["xsd"]).name
    assert len(result.get("errors") or []) == 0
    # C01 vs plain 4.1 → invalid with exactly 2 known_deltas
    xsd41 = DEXPI13 / "xsd" / "ProteusPIDSchema_4.1.xsd"
    bad = validate_xsd(path, xsd41)
    assert bad["ok"] is False
    assert bad["status"] == "invalid"
    assert len(bad["known_deltas"]) == 2


def test_sources_md_lists_urls_and_sha():
    text = (PUBLIC / "SOURCES.md").read_text(encoding="utf-8")
    assert "https://" in text
    assert "sha256" in text.lower() or C01_SHA in text
    assert "CC-BY-4.0" in text or "CC-BY" in text
    assert "C08" in text  # WALL note
    assert not (PUBLIC / "synthetic_dexpi_plantmodel.xml").exists()


def test_license_vendored():
    lic = (DEXPI13 / "LICENSE").read_text(encoding="utf-8", errors="replace")
    assert "Attribution 4.0" in lic or "Creative Commons" in lic


def test_c01_nozzle_size_and_drawing_xy():
    g = load_fixture("C01V04-VER.EX01.xml")
    sized = [n for n in g.nozzles.values() if n.size]
    assert len(sized) >= 19
    assert any(n.size and "80" in n.size for n in sized)
    # drawing_xy from Position/Location; plant XYZ stay None
    with_xy = [n for n in g.nozzles.values() if n.drawing_xy is not None]
    assert len(with_xy) >= 19
    assert all(n.x is None and n.y is None and n.z is None for n in with_xy)


def test_c08_cross_file_opc_joins():
    from threadforge.ingest_dexpi import load_fixtures_multi

    c08 = DEXPI13 / "pids" / "c08"
    xmls = sorted(c08.glob("*.xml"))
    assert len(xmls) >= 2
    g = load_fixtures_multi(xmls)
    joins = [
        e
        for e in g.from_tos.values()
        if e.connection_type == "opc_cross_page" or e.metadata.get("opc_cross_file")
    ]
    assert g.metadata.get("opc_join_count") == len(joins) == 1
