"""B11: rack tier table + A* prefers process high / utility mid / drains low."""

from __future__ import annotations

from pathlib import Path

from threadforge.clash import clash_check, segment_distance
from threadforge.ingest_dexpi import load_fixture
from threadforge.rack import (
    DEFAULT_TIER_Z,
    RICH_TIER_PIN,
    assign_rack_tier,
    median_z_in_rack,
    rack_xy_aabb,
    rich_tier_assignment,
    three_service_rack_graph,
)
from threadforge.routing import generate_routes_astar

ROOT = Path(__file__).resolve().parents[1]


def test_service_tier_table_documented():
    docs = (ROOT / "docs" / "rack_tiers.md").read_text(encoding="utf-8")
    assert "`high`" in docs and "`mid`" in docs and "`low`" in docs
    assert "PROCESS" in docs and "UTILITY" in docs and "DRAIN" in docs
    assert assign_rack_tier("FEED") == "high"
    assert assign_rack_tier("GAS") == "high"
    assert assign_rack_tier("UTILITY") == "mid"
    assert assign_rack_tier("STEAM") == "mid"
    assert assign_rack_tier("DRAIN") == "low"


def test_rich_tier_assignment_pinned():
    g = load_fixture("sample_pid_rich.xml")
    got = rich_tier_assignment(g)
    assert got == RICH_TIER_PIN
    generate_routes_astar(g)
    for lid, tier in RICH_TIER_PIN.items():
        assert g.routes[lid]["rack_tier"] == tier


def test_astar_prefers_tiers_no_capsule_overlap():
    g = three_service_rack_graph()
    art = generate_routes_astar(g, grid=0.5)
    routes = {r["line_id"]: r for r in art.payload["routes"]}
    assert set(routes) == {"L-RACK-P", "L-RACK-U", "L-RACK-D"}
    xy = rack_xy_aabb(g)
    assert xy is not None
    zp = median_z_in_rack(routes["L-RACK-P"]["points"], xy)
    zu = median_z_in_rack(routes["L-RACK-U"]["points"], xy)
    zd = median_z_in_rack(routes["L-RACK-D"]["points"], xy)
    assert zp is not None and zu is not None and zd is not None
    assert zp > zu > zd
    assert abs(zp - DEFAULT_TIER_Z["high"]) <= 1.0
    assert abs(zu - DEFAULT_TIER_Z["mid"]) <= 1.0
    assert abs(zd - DEFAULT_TIER_Z["low"]) <= 1.0
    # Share the rack without capsule overlap (computed segment distance).
    report = clash_check(g, routes=list(routes.values()), clearance=0.025)
    assert report["hard_count"] == 0
    ids = ["L-RACK-P", "L-RACK-U", "L-RACK-D"]
    for i in range(3):
        for j in range(i + 1, 3):
            p1 = [(p["x"], p["y"], p["z"]) for p in routes[ids[i]]["points"]]
            p2 = [(p["x"], p["y"], p["z"]) for p in routes[ids[j]]["points"]]
            best = 1e9
            for a, b in zip(p1, p1[1:]):
                for c, d in zip(p2, p2[1:]):
                    dist, _, _ = segment_distance(a, b, c, d)
                    best = min(best, dist)
            assert best > 0.05, (ids[i], ids[j], best)
