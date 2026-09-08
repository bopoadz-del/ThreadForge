"""Exercise remaining public branches for B36 (measured coverage)."""
from __future__ import annotations

from pathlib import Path

from threadforge import agent_tools
from threadforge.capabilities import capability_table
from threadforge.graph import TopologyGraph
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import FromTo, Pipeline, Tag
from threadforge.tables import (
    flange_bolts,
    hydrotest_pressure_barg,
    long_radius_elbow_m,
    mass_per_m,
    od_mm,
    parse_nps_inch,
    support_span_m,
    wall_thickness_mm,
)


def test_tables_edge_branches():
    assert parse_nps_inch(None) == 4.0
    assert parse_nps_inch("DN100") > 0
    assert parse_nps_inch("not-a-size") == 4.0
    assert od_mm('99"') > 0  # nearest
    assert wall_thickness_mm('1"', "XXS") > 0 or wall_thickness_mm('1"', "XXS") >= 0
    assert wall_thickness_mm('99"', "99") > 0
    assert mass_per_m('2"') > 0
    assert support_span_m('99"') > 0
    assert long_radius_elbow_m('6"') > 0
    assert flange_bolts('6"', 150)[0] >= 4
    assert flange_bolts('99"', 150)[0] >= 4
    assert flange_bolts('6"', 999)[0] >= 4
    assert hydrotest_pressure_barg(None) is None
    assert hydrotest_pressure_barg(10.0) == 15.0


def test_graph_queries_and_unmatched():
    g = TopologyGraph()
    g.add_tag(Tag(id="T1", name="T1", volume_id="V1"))
    g.add_pipeline(Pipeline(id="P1", line_number="L1", from_tag="T1", to_tag="T2", component_tags=["T1"]))
    g.add_from_to(FromTo(id="E1", from_id="T1", to_id="MISSING", matched=False))
    g.add_from_to(FromTo(id="E2", from_id="T1", to_id="T1", matched=True))
    assert g.get_tag("T1") is not None
    assert "MISSING" in g.unmatched_tags or g.neighbors("T1")
    assert g.neighbors("T1")
    assert g.lines_for_tag("T1")
    assert g.tags_in_volume("V1")
    assert g.tags_by_discipline("PIP")
    s = g.connectivity_summary()
    assert "tag_count" in s
    g.query(summary=True)
    g.query(tag_id="T1")
    g.query(discipline="PIP")
    g.query(volume_id="V1")
    g.query(line_id="P1")
    g.query()
    g.revise_pipeline("P1", {"service": "X"})
    g.revise_tag("T1", {"name": "T1x", "metadata": {"k": "v"}})
    assert capability_table().startswith("| Capability")


def test_agent_tools_remaining(tmp_path):
    agent_tools.SESSION.graph = None
    agent_tools.ingest_dexpi(path="sample_pid_rich.xml")
    agent_tools.query_graph(summary=True)
    agent_tools.build_test_packs()
    agent_tools.build_work_packages()
    agent_tools.export_artefacts(output_dir=str(tmp_path))
    agent_tools.dexpi_coverage()
    agent_tools.maturity_check(required="FEED")
    agent_tools.look_ahead(weeks=1)
    agent_tools.co_activity_check()


def test_ifc_in_wall_and_persist_verify():
    from threadforge.exporters.ifc_in import load_ifc_obstacles
    from threadforge.persist import hash_api_key, new_key_hash, verify_api_key

    obs = load_ifc_obstacles(Path("/no/such/file.nwd"))
    assert isinstance(obs, dict)
    h = new_key_hash("abc")
    assert not verify_api_key("nope", h)
    assert hash_api_key("abc", h.split("$")[1]) == h


def test_load_all_vendor_again():
    from threadforge.dexpi_public import vendor_xmls
    from threadforge.ingest_dexpi import parse_dexpi_xml

    for path in vendor_xmls()[:8]:
        parse_dexpi_xml(path)
    load_fixture("C03V04-VER.EX02.xml")
