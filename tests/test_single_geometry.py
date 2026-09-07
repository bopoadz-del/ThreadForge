"""E1: one shared A* geometry for routes / PCF / iso / IFC / quantities."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from threadforge.exporters.ifc import export_ifc4
from threadforge.generators import (
    export_all_piping_artefacts,
)
from threadforge.ingest_dexpi import load_fixture
from threadforge.pcf_reader import parse_pcf
from threadforge.routing import ensure_routes


def _ifc_axis_length_for_line(ifc_path: Path, line_number: str) -> float:
    try:
        import ifcopenshell
    except ImportError:
        pytest.skip("ifcopenshell not installed")
    model = ifcopenshell.open(str(ifc_path))
    total = 0.0
    for seg in model.by_type("IfcPipeSegment"):
        desc = seg.Description or ""
        if f"LINE={line_number}" not in desc and f"LINE={line_number};" not in desc:
            # Description embeds LINE=<line>
            if f"LINE={line_number}" not in desc:
                continue
        m = re.search(r"LENGTH_M=([0-9.]+)", desc)
        if m:
            total += float(m.group(1))
    return total


def test_single_geometry_all_artefacts_agree(tmp_path: Path):
    """For every non-fabricated line, all artefact geometries agree within 1 mm."""
    g = load_fixture()  # demo path fixture
    out = tmp_path / "out"
    export_all_piping_artefacts(g, out)

    routes_payload = json.loads((out / "routes" / "routes.json").read_text(encoding="utf-8"))
    routes_by_id = {r["line_id"]: r for r in routes_payload["routes"]}
    qty = json.loads((out / "qty" / "quantities.json").read_text(encoding="utf-8"))
    qty_by_id = {r["line_id"]: r for r in qty["rows"]}

    # Demo non-fabricated routes must be A* with length_source == astar
    non_fab = [
        r for r in routes_payload["routes"] if r.get("geometry_source") != "fabricated"
    ]
    assert non_fab, "expected at least one non-fabricated demo line"
    for r in non_fab:
        assert r.get("accuracy") == "astar", r
        assert r.get("length_source") == "astar", r

    # IFC from shared routes
    ifc_path = out / "ifc" / "model.ifc"
    try:
        export_ifc4(g, ifc_path)
    except ImportError:
        ifc_path = None

    for lid, pipe in g.pipelines.items():
        route = routes_by_id[lid]
        if route.get("geometry_source") == "fabricated":
            continue
        route_len = float(route["length_m"])
        route_pts = [(p["x"], p["y"], p["z"]) for p in route["points"]]

        # quantities
        assert abs(float(qty_by_id[lid]["length_m"]) - route_len) < 0.001
        assert qty_by_id[lid]["length_source"] == "astar"

        # iso JSON route points / length
        safe = pipe.line_number.replace("/", "_").replace(" ", "_")
        iso = json.loads((out / "iso" / f"{safe}.iso.json").read_text(encoding="utf-8"))
        iso_pts = [(p["x"], p["y"], p["z"]) for p in iso["route"]["points"]]
        assert len(iso_pts) == len(route_pts)
        for a, b in zip(iso_pts, route_pts):
            assert math.dist(a, b) < 0.001
        assert abs(float(iso["route"]["length_m"]) - route_len) < 0.001

        # PCF END-POINTs (mm÷1000) — centreline length within 1 mm of route
        # (elbows shorten geometric chord slightly vs raw polyline; compare
        # start/end and that each END-POINT lies on the shared route polyline)
        pcf_text = (out / "pcf" / f"{safe}.pcf").read_text(encoding="utf-8")
        doc = parse_pcf(pcf_text)
        end_pts_m = []
        for c in doc.components:
            if c.kind == "SUPPORT":
                continue
            for ep in c.end_points:
                end_pts_m.append((ep.x / 1000.0, ep.y / 1000.0, ep.z / 1000.0))
        assert end_pts_m, f"no PCF endpoints for {pipe.line_number}"
        # First/last END-POINT match route ends within 1 mm
        assert math.dist(end_pts_m[0], route_pts[0]) < 0.001
        assert math.dist(end_pts_m[-1], route_pts[-1]) < 0.001
        # Every END-POINT within 1 mm of some route segment
        for ep in end_pts_m:
            best = min(
                _point_seg_dist(ep, route_pts[i], route_pts[i + 1])
                for i in range(len(route_pts) - 1)
            )
            assert best < 0.001, f"{pipe.line_number} PCF pt {ep} off route by {best}"

        # IFC axis length for this line agrees within 1 mm
        if ifc_path is not None:
            ifc_len = _ifc_axis_length_for_line(ifc_path, pipe.line_number)
            assert abs(ifc_len - route_len) < 0.001, (
                f"IFC {pipe.line_number}: {ifc_len} vs route {route_len}"
            )

    # graph.routes is the single store
    ensure_routes(g)
    assert set(g.routes) == set(g.pipelines)


def _point_seg_dist(p, a, b) -> float:
    ax, ay, az = a
    bx, by, bz = b
    px, py, pz = p
    vx, vy, vz = bx - ax, by - ay, bz - az
    leng2 = vx * vx + vy * vy + vz * vz
    if leng2 < 1e-18:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy + (pz - az) * vz) / leng2))
    q = (ax + t * vx, ay + t * vy, az + t * vz)
    return math.dist(p, q)


def test_no_direct_route_pipeline_in_artefact_modules():
    """Guards the E1 invariant: artefact modules never call route_pipeline."""
    root = Path(__file__).resolve().parents[1] / "src" / "threadforge"
    offenders = []
    for rel in (
        "generators.py",
        "clash.py",
        "maturity.py",
        "exporters/ifc.py",
        "exporters/dxf.py",
        "agent_tools.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "route_pipeline(" in line and "def route_pipeline" not in line:
                offenders.append(f"{rel}:{i}:{line.strip()}")
    assert offenders == [], offenders
