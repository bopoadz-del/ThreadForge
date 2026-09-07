"""D3: obstacle-aware A* routing invariants."""

from __future__ import annotations

import math

from threadforge.graph import TopologyGraph
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import DesignVolume, Equipment, Nozzle, Pipeline
from threadforge.routing import (
    _point_in_aabb,
    generate_routes_astar,
    route_astar,
    route_pipeline_astar,
)


def _sample_polyline(points: list[dict], step: float = 0.1):
    pts = [(p["x"], p["y"], p["z"]) for p in points]
    out = []
    for a, b in zip(pts, pts[1:]):
        leng = math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))
        n = max(1, int(leng / step))
        for i in range(n + 1):
            t = i / n
            out.append(tuple(a[j] + t * (b[j] - a[j]) for j in range(3)))
    return out


def test_astar_avoids_aabb_obstacle():
    start = (0.0, 0.0, 5.0)
    end = (10.0, 0.0, 5.0)
    # Wall box blocking straight line
    box = (4.0, -1.0, 4.0, 6.0, 1.0, 6.0)
    res = route_astar(start, end, obstacles={"aabbs": [box], "capsules": [], "volumes": []}, grid=0.5)
    assert res["accuracy"] == "astar"
    for p in res["points"]:
        # endpoints may touch; interior must not be inside
        if p in (start, end):
            continue
    samples = []
    pts = res["points"]
    for a, b in zip(pts, pts[1:]):
        for i in range(11):
            t = i / 10
            samples.append(tuple(a[j] + t * (b[j] - a[j]) for j in range(3)))
    # Interior samples (skip first/last) must clear the box
    for p in samples[1:-1]:
        assert not _point_in_aabb(p, box), p


def test_drain_z_non_increasing():
    g = load_fixture("sample_pid_rich.xml")
    pipe = g.pipelines["LINE-200-D-1010"]
    r = route_pipeline_astar(g, pipe)
    zs = [p["z"] for p in r["points"]]
    # From N3 z=10 to N4 z=10 — flat OK; if any drop, must be monotonic non-increasing from source
    # Build crafted drain with drop
    res = route_astar(
        (0.0, 0.0, 10.0),
        (8.0, 0.0, 6.0),
        obstacles={"aabbs": [], "capsules": [], "volumes": []},
        grid=0.5,
        drain_monotonic=True,
    )
    assert res["accuracy"] == "astar"
    zs = [p[2] for p in res["points"]]
    for a, b in zip(zs, zs[1:]):
        assert b <= a + 1e-9, (zs, res)


def test_two_crossing_lines_min_separation():
    """Two lines whose straight paths cross are routed with min separation ≥ r1+r2+c."""
    g = TopologyGraph()
    g.volumes["V"] = DesignVolume(id="V", name="V", xmin=-5, ymin=-5, zmin=0, xmax=20, ymax=20, zmax=15)
    g.equipment["E1"] = Equipment(id="E1", tag="E1", nozzles=["E1-N1"], volume_id="V")
    g.equipment["E2"] = Equipment(id="E2", tag="E2", nozzles=["E2-N1"], volume_id="V")
    g.equipment["E3"] = Equipment(id="E3", tag="E3", nozzles=["E3-N1"], volume_id="V")
    g.equipment["E4"] = Equipment(id="E4", tag="E4", nozzles=["E4-N1"], volume_id="V")
    g.nozzles["E1-N1"] = Nozzle(id="E1-N1", tag="N1", equipment_id="E1", x=0, y=5, z=5)
    g.nozzles["E2-N1"] = Nozzle(id="E2-N1", tag="N1", equipment_id="E2", x=10, y=5, z=5)
    g.nozzles["E3-N1"] = Nozzle(id="E3-N1", tag="N1", equipment_id="E3", x=5, y=0, z=5)
    g.nozzles["E4-N1"] = Nozzle(id="E4-N1", tag="N1", equipment_id="E4", x=5, y=10, z=5)
    g.pipelines["L1"] = Pipeline(
        id="L1", line_number="L1", from_tag="E1-N1", to_tag="E2-N1", nominal_bore='2"', service="PROCESS"
    )
    g.pipelines["L2"] = Pipeline(
        id="L2", line_number="L2", from_tag="E3-N1", to_tag="E4-N1", nominal_bore='2"', service="PROCESS"
    )
    art = generate_routes_astar(g, grid=0.5)
    routes = {r["line_id"]: r for r in art.payload["routes"]}
    r1, r2 = routes["L1"], routes["L2"]
    # Min separation between polylines
    c = 0.025
    rad = 50.0 / 2000.0  # ~2" bore_to_mm/2000
    min_sep = 2 * rad + c
    best = 1e9
    from threadforge.routing import _point_segment_distance

    pts1 = [(p["x"], p["y"], p["z"]) for p in r1["points"]]
    pts2 = [(p["x"], p["y"], p["z"]) for p in r2["points"]]
    for a, b in zip(pts1, pts1[1:]):
        for i in range(11):
            t = i / 10
            p = tuple(a[j] + t * (b[j] - a[j]) for j in range(3))
            for c1, c2 in zip(pts2, pts2[1:]):
                d = _point_segment_distance(p, c1, c2)
                best = min(best, d)
    # If A* respected prior capsules, separation should hold (allow tiny numeric slack)
    assert best + 1e-6 >= min_sep
    # Stronger: no exact shared interior point
    assert best > 0.01


def test_rich_routes_prefer_astar():
    g = load_fixture("sample_pid_rich.xml")
    art = generate_routes_astar(g)
    accuracies = {r["line_number"]: r["accuracy"] for r in art.payload["routes"]}
    assert any(a == "astar" for a in accuracies.values())
