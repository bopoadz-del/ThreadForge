"""B14: clash categories — structure, insulation OD, access hemisphere."""

from __future__ import annotations

from threadforge.clash import ACCESS_HEMISPHERE_M, ACCESS_RULE, clash_check
from threadforge.exporters.ifc_in import attach_ifc_obstacles, public_rack_path
from threadforge.graph import TopologyGraph
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import Equipment, Nozzle, Pipeline
from threadforge.routing import generate_routes_astar


def _line(g: TopologyGraph, lid: str, a: tuple[float, float, float], b: tuple[float, float, float], **meta: object) -> None:
    ea, eb = f"{lid}-A", f"{lid}-B"
    na, nb = f"{ea}-N", f"{eb}-N"
    g.equipment[ea] = Equipment(id=ea, tag=ea, nozzles=[na])
    g.equipment[eb] = Equipment(id=eb, tag=eb, nozzles=[nb])
    g.nozzles[na] = Nozzle(id=na, tag="N", equipment_id=ea, x=a[0], y=a[1], z=a[2])
    g.nozzles[nb] = Nozzle(id=nb, tag="N", equipment_id=eb, x=b[0], y=b[1], z=b[2])
    g.pipelines[lid] = Pipeline(
        id=lid,
        line_number=lid,
        from_tag=na,
        to_tag=nb,
        nominal_bore='6"',
        service="PROCESS",
        metadata=dict(meta),
    )
    g.routes[lid] = {
        "line_id": lid,
        "line_number": lid,
        "from": na,
        "to": nb,
        "nominal_bore": '6"',
        "geometry_source": "nozzle_xyz",
        "insulation_mm": meta.get("insulation_mm", 0),
        "points": [{"x": a[0], "y": a[1], "z": a[2]}, {"x": b[0], "y": b[1], "z": b[2]}],
    }


def test_rich_plus_ifc_hard_zero():
    g = load_fixture("sample_pid_rich.xml")
    attach_ifc_obstacles(g, public_rack_path())
    generate_routes_astar(g)
    report = clash_check(g)
    assert report["hard_count"] == 0, report["hard"][:3]


def test_crafted_one_each_category():
    g = TopologyGraph()
    # Structure: pipe through a 2 m cube.
    _line(g, "L-STR", (0.0, 0.0, 5.0), (10.0, 0.0, 5.0))
    g.metadata["structure_aabbs"] = [(4.0, -1.0, 4.0, 6.0, 1.0, 6.0)]
    # Insulation: parallel 6" (r≈0.084) 0.22 m apart, 50 mm insulation each.
    _line(g, "L-INS-A", (0.0, 5.0, 2.0), (10.0, 5.0, 2.0), insulation_mm=50.0)
    _line(g, "L-INS-B", (0.0, 5.22, 2.0), (10.0, 5.22, 2.0), insulation_mm=50.0)
    # Access: valve hemisphere on L-ACC-V; L-ACC-X clips it at +Z.
    _line(g, "L-ACC-V", (0.0, 10.0, 3.0), (4.0, 10.0, 3.0))
    _line(g, "L-ACC-X", (2.0, 10.15, 3.1), (2.0, 12.0, 3.1))
    g.metadata["access_valves"] = [{"id": "HV-1", "line_id": "L-ACC-V", "xyz": (2.0, 10.0, 3.0)}]
    report = clash_check(g, routes=list(g.routes.values()))
    by = report["hard_by_category"]
    assert by.get("pipe_vs_structure", 0) >= 1, by
    assert by.get("insulation", 0) >= 1, by
    assert by.get("access", 0) >= 1, by
    assert report["access_hemisphere_m"] == ACCESS_HEMISPHERE_M == 0.6
    assert "PNF0200" in ACCESS_RULE
    assert "PNF0200" in report["access_rule"]
