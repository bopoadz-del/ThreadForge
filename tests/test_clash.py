"""D4: capsule clash math with hand-computed distances."""

from __future__ import annotations

from threadforge.clash import (
    capsule_aabb,
    capsule_capsule,
    capsule_cylinder,
    clash_check,
    generate_clash_report,
    segment_distance,
)
from threadforge.graph import TopologyGraph
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import DesignVolume, Equipment, Nozzle, Pipeline
from threadforge.routing import generate_routes_astar


def test_segment_distance_parallel():
    # Parallel segments 1 m apart in Y
    d, c1, c2 = segment_distance((0, 0, 0), (10, 0, 0), (0, 1, 0), (10, 1, 0))
    assert abs(d - 1.0) < 1e-9


def test_segment_distance_skew():
    # Skew lines: x-axis and parallel to y at z=2, x=1
    d, _, _ = segment_distance((0, 0, 0), (10, 0, 0), (1, -5, 2), (1, 5, 2))
    assert abs(d - 2.0) < 1e-9


def test_segment_distance_touching():
    d, _, _ = segment_distance((0, 0, 0), (1, 0, 0), (1, 0, 0), (2, 0, 0))
    assert abs(d) < 1e-9


def test_segment_distance_contained_point():
    # Point on segment
    d, c1, c2 = segment_distance((0, 0, 0), (0, 0, 0), (0, 0, 0), (5, 0, 0))
    assert abs(d) < 1e-9


def test_capsule_capsule_hard():
    # Radii 0.3 + 0.3, centreline 0.5 apart → penetration 0.1
    r = capsule_capsule((0, 0, 0), (10, 0, 0), 0.3, (0, 0.5, 0), (10, 0.5, 0), 0.3)
    assert r["hard"] is True
    assert abs(r["penetration"] - 0.1) < 1e-9


def test_capsule_aabb_and_cylinder():
    box = (4.0, -1.0, -1.0, 6.0, 1.0, 1.0)
    hit = capsule_aabb((0, 0, 0), (10, 0, 0), 0.1, box)
    assert hit["hard"] is True
    cyl = capsule_cylinder((0, 0, 0), (10, 0, 0), 0.2, (5, 0.3, 0), (5, 0.3, 5), 0.2)
    assert cyl["distance"] < 0.35


def test_clash_check_crossing_fixture():
    g = TopologyGraph()
    g.volumes["V"] = DesignVolume(id="V", name="V", xmin=-5, ymin=-5, zmin=0, xmax=20, ymax=20, zmax=15)
    for eid, nid, xyz in [
        ("E1", "E1-N1", (0, 5, 5)),
        ("E2", "E2-N1", (10, 5, 5)),
        ("E3", "E3-N1", (5, 0, 5)),
        ("E4", "E4-N1", (5, 10, 5)),
    ]:
        g.equipment[eid] = Equipment(id=eid, tag=eid, nozzles=[nid], volume_id="V")
        g.nozzles[nid] = Nozzle(id=nid, tag="N1", equipment_id=eid, x=xyz[0], y=xyz[1], z=xyz[2])
    g.pipelines["L1"] = Pipeline(
        id="L1", line_number="L1", from_tag="E1-N1", to_tag="E2-N1", nominal_bore='6"', service="PROCESS"
    )
    g.pipelines["L2"] = Pipeline(
        id="L2", line_number="L2", from_tag="E3-N1", to_tag="E4-N1", nominal_bore='6"', service="PROCESS"
    )
    # Force naive crossing routes (not A*) to guarantee a clash report
    routes = [
        {
            "line_id": "L1",
            "line_number": "L1",
            "nominal_bore": '6"',
            "points": [{"x": 0, "y": 5, "z": 5}, {"x": 10, "y": 5, "z": 5}],
        },
        {
            "line_id": "L2",
            "line_number": "L2",
            "nominal_bore": '6"',
            "points": [{"x": 5, "y": 0, "z": 5}, {"x": 5, "y": 10, "z": 5}],
        },
    ]
    report = clash_check(g, routes=routes, clearance=0.05)
    assert report["hard_count"] >= 1


def test_rich_astar_clash_empty_or_soft_only():
    g = load_fixture("sample_pid_rich.xml")
    routes = generate_routes_astar(g).payload["routes"]
    report = clash_check(g, routes=routes, clearance=0.025)
    # A* should keep hard clashes at zero for the rich fixture
    assert report["hard_count"] == 0


def test_clash_report_writes(tmp_path):
    g = load_fixture("sample_pid_rich.xml")
    art = generate_clash_report(g, output_dir=tmp_path)
    assert art.status == "ready"
    assert (tmp_path / "clash" / "clash_report.json").exists()


def test_demo_path_clash_hard_count_zero(tmp_path):
    """E2: demo export path (same as demos/run_demo artefacts) → hard_count == 0."""
    import json

    from threadforge.generators import export_all_piping_artefacts

    g = load_fixture()  # sample_pid.xml — demo default
    out = tmp_path / "demo_out"
    export_all_piping_artefacts(g, out)
    report_path = out / "clash" / "clash_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["hard_count"] == 0, report
    assert "120-P-1002" in report.get("excluded_fabricated", []) or any(
        "1002" in str(x) for x in report.get("excluded_fabricated", [])
    )
    # Shared-nozzle pair must not appear as clash entries
    for c in report.get("clashes", []):
        tags = set(c.get("tags") or [])
        assert not ({"120-P-1001", "124-LPWP-2505"} <= tags)


def test_shared_nozzle_pair_zero_entries():
    """E2: lines sharing a nozzle produce zero clash entries."""
    g = TopologyGraph()
    g.volumes["V"] = DesignVolume(id="V", name="V", xmin=-5, ymin=-5, zmin=0, xmax=20, ymax=20, zmax=15)
    for eid, nid, xyz in [
        ("E1", "SHARED-N1", (0, 0, 5)),
        ("E2", "E2-N1", (10, 0, 5)),
        ("E3", "E3-N1", (0, 10, 5)),
    ]:
        g.equipment[eid] = Equipment(id=eid, tag=eid, nozzles=[nid], volume_id="V")
        g.nozzles[nid] = Nozzle(id=nid, tag="N", equipment_id=eid, x=xyz[0], y=xyz[1], z=xyz[2])
    # Fix SHARED nozzle parent — both lines use SHARED-N1
    g.equipment["E1"] = Equipment(id="E1", tag="E1", nozzles=["SHARED-N1"], volume_id="V")
    g.nozzles["SHARED-N1"] = Nozzle(id="SHARED-N1", tag="N1", equipment_id="E1", x=0, y=0, z=5)
    g.pipelines["L1"] = Pipeline(
        id="L1", line_number="L1", from_tag="SHARED-N1", to_tag="E2-N1", nominal_bore='6"', service="PROCESS"
    )
    g.pipelines["L2"] = Pipeline(
        id="L2", line_number="L2", from_tag="SHARED-N1", to_tag="E3-N1", nominal_bore='6"', service="PROCESS"
    )
    routes = [
        {
            "line_id": "L1",
            "line_number": "L1",
            "from": "SHARED-N1",
            "to": "E2-N1",
            "nominal_bore": '6"',
            "geometry_source": "nozzle_xyz",
            "points": [{"x": 0, "y": 0, "z": 5}, {"x": 10, "y": 0, "z": 5}],
        },
        {
            "line_id": "L2",
            "line_number": "L2",
            "from": "SHARED-N1",
            "to": "E3-N1",
            "nominal_bore": '6"',
            "geometry_source": "nozzle_xyz",
            "points": [{"x": 0, "y": 0, "z": 5}, {"x": 0, "y": 10, "z": 5}],
        },
    ]
    report = clash_check(g, routes=routes, clearance=0.05)
    assert report["clashes"] == []
    assert report["hard_count"] == 0
    assert report["skipped_shared_connection_pairs"] >= 1


def test_fabricated_excluded_from_clash():
    """E2: fabricated geometry is excluded and listed."""
    g = TopologyGraph()
    g.volumes["V"] = DesignVolume(id="V", name="V", xmin=-5, ymin=-5, zmin=0, xmax=20, ymax=20, zmax=15)
    g.equipment["E1"] = Equipment(id="E1", tag="E1", nozzles=["N1"], volume_id="V")
    g.nozzles["N1"] = Nozzle(id="N1", tag="N1", equipment_id="E1", x=0, y=0, z=5)
    g.equipment["E2"] = Equipment(id="E2", tag="E2", nozzles=["N2"], volume_id="V")
    g.nozzles["N2"] = Nozzle(id="N2", tag="N2", equipment_id="E2", x=10, y=0, z=5)
    g.pipelines["L1"] = Pipeline(id="L1", line_number="L1", from_tag="N1", to_tag="N2", nominal_bore='4"')
    g.pipelines["LF"] = Pipeline(id="LF", line_number="LFAB", from_tag="N1", to_tag="N2", nominal_bore='4"')
    routes = [
        {
            "line_id": "L1",
            "line_number": "L1",
            "from": "N1",
            "to": "N2",
            "nominal_bore": '4"',
            "geometry_source": "nozzle_xyz",
            "points": [{"x": 0, "y": 0, "z": 5}, {"x": 10, "y": 0, "z": 5}],
        },
        {
            "line_id": "LF",
            "line_number": "LFAB",
            "from": "N1",
            "to": "N2",
            "nominal_bore": '4"',
            "geometry_source": "fabricated",
            "points": [{"x": 0, "y": 0.01, "z": 5}, {"x": 10, "y": 0.01, "z": 5}],
        },
    ]
    report = clash_check(g, routes=routes)
    assert "LFAB" in report["excluded_fabricated"]
    assert report["hard_count"] == 0
