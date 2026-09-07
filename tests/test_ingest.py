"""Parse fixture → graph with tags/lines/from-to/battery limits."""

from threadforge.ingest_dexpi import load_fixture, parse_dexpi_xml
from threadforge.models import Discipline


def test_parse_fixture_counts():
    g = load_fixture()
    s = g.connectivity_summary()
    assert s["sheet_count"] == 2
    assert s["equipment_count"] >= 2
    assert s["pipeline_count"] >= 3
    assert s["from_to_count"] >= 3
    assert s["battery_limit_count"] == 2
    assert s["volume_count"] == 3
    assert s["system_count"] == 2
    assert s["tag_count"] > 10


def test_selected_equipment_identity():
    g = load_fixture()
    tag = g.get_tag("120-VEPR-2010")
    assert tag is not None
    assert tag.identity.std_name == "120-VEPR-2010"
    assert tag.identity.ccs_base == "VEPR"
    assert tag.asset_3d_ref == "TS001"
    assert tag.geometry_bounds is not None
    assert tag.volume_id == "VOL-A"
    eq = g.equipment["120-VEPR-2010"]
    assert "120-VEPR-2010-N1" in eq.nozzles


def test_from_to_and_battery_limits():
    g = load_fixture()
    assert "FT-LINE-120-P-1001" in g.from_tos
    edge = g.from_tos["FT-LINE-120-P-1001"]
    assert edge.matched is True
    assert edge.from_id == "120-VEPR-2010-N1"
    bl = g.battery_limits["BL-001"]
    assert bl.tag_id == "124-LPNP-2508"


def test_instrument_discipline():
    g = load_fixture()
    pt = g.instruments["120-PT-2010"]
    assert pt.discipline == Discipline.INS
    assert g.tags["120-PT-2010"].discipline == Discipline.INS


def test_parse_bytes():
    from threadforge.ingest_dexpi import default_fixture_path

    raw = default_fixture_path().read_bytes()
    g = parse_dexpi_xml(raw)
    assert len(g.tags) > 0
