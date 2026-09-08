"""B10: IFC-in structure/equipment → AABB/capsule; 4 lines clear obstacles."""

from __future__ import annotations

from pathlib import Path

import pytest

from threadforge.exporters.ifc_in import (
    attach_ifc_obstacles,
    four_line_ifc_graph,
    load_ifc_obstacles,
    public_rack_path,
    route_ifc_penetrations,
)
from threadforge.routing import generate_routes_astar

pytest.importorskip("ifcopenshell")

ROOT = Path(__file__).resolve().parents[1]


def test_walled_cad_returns_empty(caplog):
    import logging

    dummy = ROOT / "tests" / "no_such.nwd"
    with caplog.at_level(logging.WARNING, logger="threadforge.ifc_in"):
        obs = load_ifc_obstacles(dummy)
    assert obs["wall"] == "cad_reader"
    assert obs["aabbs"] == []
    assert any("WALL" in r.message and "NWD" in r.message for r in caplog.records)


def test_ifc_in_reads_structure_and_equipment():
    path = public_rack_path()
    obs = load_ifc_obstacles(path)
    assert obs["wall"] is None
    assert obs["structure_count"] >= 7
    assert obs["equipment_count"] >= 1
    assert len(obs["aabbs"]) == len(obs["products"])
    assert len(obs["capsules"]) == len(obs["products"])
    kinds = {p["ifc_class"] for p in obs["products"]}
    assert "IfcColumn" in kinds
    assert "IfcBeam" in kinds
    assert "IfcTank" in kinds
    # Bounding-box transform must be computed (non-zero extent)
    for box in obs["aabbs"]:
        assert box[3] > box[0] and box[5] > box[2]


def test_four_lines_zero_ifc_penetration():
    path = public_rack_path()
    obs = load_ifc_obstacles(path)
    g = four_line_ifc_graph()
    attach_ifc_obstacles(g, path)
    art = generate_routes_astar(g, grid=0.5)
    routes = art.payload["routes"]
    assert len(routes) == 4
    assert all(r.get("accuracy") == "astar" for r in routes)
    hits = route_ifc_penetrations(routes, obs["aabbs"], skip_endpoints=True, samples=24)
    assert hits == 0, (hits, [(r["line_id"], r["points"]) for r in routes])
