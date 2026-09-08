"""B12: MSS SP-58 kinematic support types, pinned on the rich fixture."""

from __future__ import annotations

from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import generate_routes_astar
from threadforge.supports_mss import MSS_TYPE, SPRING_VERTICAL_M, support_types_kinematic, type_counts


def test_mss_types_cited():
    assert MSS_TYPE["anchor"] == "Type 40"
    assert MSS_TYPE["guide"] == "Type 42"
    assert MSS_TYPE["shoe"] == "Type 1"
    assert MSS_TYPE["spring_hanger"] == "Type 51"
    from threadforge import supports_mss as M

    assert "MSS SP-58" in (M.__doc__ or "")


def test_anchor_guide_shoe_spring_rules():
    # 20 m horizontal 6" insulated → anchors + shoes + guides
    pts = [(0.0, 0.0, 5.0), (20.0, 0.0, 5.0)]
    ins = support_types_kinematic(pts, '6"', insulated=True)
    counts = type_counts(ins)
    assert counts["anchor"] == 2
    assert counts["shoe"] >= 1
    assert counts["guide"] >= 1
    assert counts["spring_hanger"] == 0
    bare = support_types_kinematic(pts, '6"', insulated=False)
    assert type_counts(bare)["shoe"] == 0
    # 7 m riser
    riser = [(0.0, 0.0, 0.0), (0.0, 0.0, 7.0)]
    spr = support_types_kinematic(riser, '4"', insulated=False)
    assert type_counts(spr)["spring_hanger"] >= 1
    assert abs(7.0) > SPRING_VERTICAL_M
    assert all(s["mss_sp58"] in MSS_TYPE.values() for s in ins + spr)


def test_rich_supports_mss_pinned():
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    pinned = {
        lid: type_counts(g.routes[lid]["supports_mss"])
        for lid in g.pipelines
    }
    for lid, c in pinned.items():
        assert c["anchor"] == 2, (lid, c)
        assert all(s.get("standard") == "MSS SP-58" for s in g.routes[lid]["supports_mss"])
    # Measured on sample_pid_rich A* polylines + MSS SP-58 span table.
    # P-1002 has a 6.5 m riser (z 1.5→8.0) → Type 51 spring hanger.
    expected = {
        "LINE-200-P-1001": {"anchor": 2, "guide": 1, "shoe": 0, "spring_hanger": 0},
        "LINE-200-P-1002": {"anchor": 2, "guide": 5, "shoe": 0, "spring_hanger": 1},
        "LINE-210-G-2001": {"anchor": 2, "guide": 2, "shoe": 0, "spring_hanger": 0},
        "LINE-200-D-1010": {"anchor": 2, "guide": 2, "shoe": 0, "spring_hanger": 0},
    }
    assert pinned == expected
