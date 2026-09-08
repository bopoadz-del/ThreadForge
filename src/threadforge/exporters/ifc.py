"""IFC4 piping export via ifcopenshell (optional dependency).

Creates IfcProject/Site/Building/Storey structure from DesignVolumes,
IfcPipeSegment per centreline segment with Axis polyline, IfcPipeFitting
for elbows, and IfcRelConnectsPorts between consecutive segment ports.

Length is also encoded in Description as LENGTH_M=<float> for A14 reopen.
B19 validates with ifcopenshell.validate (schema + express) and measures
axis length on reopen (±0.5 %).
"""

from __future__ import annotations

import math
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import ArtefactDescriptor, ArtefactKind
from threadforge.routing import bore_to_mm, ensure_routes


def _aid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _require_ifcopenshell() -> Any:
    try:
        import ifcopenshell
        import ifcopenshell.api.aggregate
        import ifcopenshell.api.context
        import ifcopenshell.api.root
        import ifcopenshell.api.spatial
        import ifcopenshell.api.unit
        return ifcopenshell
    except ImportError as exc:
        raise ImportError(
            "ifcopenshell is required for IFC export — pip install 'threadforge[ifc]'"
        ) from exc


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))


def _route_axis_pieces(graph: TopologyGraph, route: dict[str, Any]) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Route vertex pairs when the polyline already has ≥2 segments.

    A single long run is split on shop-spool axis_points so consecutive
    IfcPipeSegment entities exist for IfcRelConnectsPorts (B19) while the
    summed axis still equals the route length.
    """
    pts = [(float(p["x"]), float(p["y"]), float(p["z"])) for p in route.get("points") or []]
    pairs = [(a, b) for a, b in zip(pts, pts[1:]) if _dist(a, b) > 1e-9]
    if len(pairs) >= 2:
        return pairs
    spools = ((route.get("spools") or {}).get("spools") if isinstance(route.get("spools"), dict) else None)
    pieces: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    if spools:
        for sp in spools:
            apts = [(float(p[0]), float(p[1]), float(p[2])) for p in (sp.get("axis_points") or [])]
            for a, b in zip(apts, apts[1:]):
                if _dist(a, b) > 1e-9:
                    pieces.append((a, b))
        if pieces:
            return pieces
    return pairs


def export_ifc4(
    graph: TopologyGraph,
    output_path: Optional[Path] = None,
    routes: Optional[list[dict[str, Any]]] = None,
) -> ArtefactDescriptor:
    """Write an IFC4 file with pipe segments/fittings approximating routes."""
    ifcopenshell = _require_ifcopenshell()
    import ifcopenshell.api.aggregate  # noqa: F811
    import ifcopenshell.api.context  # noqa: F811
    import ifcopenshell.api.geometry
    import ifcopenshell.api.root  # noqa: F811
    import ifcopenshell.api.spatial  # noqa: F811
    import ifcopenshell.api.system
    import ifcopenshell.api.unit  # noqa: F811

    if routes is None:
        ensure_routes(graph)
        routes = list(graph.routes.values())

    model = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name=graph.metadata.get("plant", "ThreadForge")
    )
    metre = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix=None)
    area = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT", prefix=None)
    volu = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT", prefix=None)
    ifcopenshell.api.unit.assign_unit(model, units=[metre, area, volu])
    context = ifcopenshell.api.context.add_context(model, context_type="Model")
    ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    axis_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Axis",
        target_view="GRAPH_VIEW",
        parent=context,
    )
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Plant")
    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])

    storeys = {}
    for vol in graph.volumes.values():
        storey = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcBuildingStorey", name=vol.name or vol.id
        )
        ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])
        storeys[vol.id] = storey
    if not storeys:
        storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="L0")
        ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])
        storeys["L0"] = storey
    default_storey = next(iter(storeys.values()))

    segment_count = 0
    fitting_count = 0
    total_length = 0.0
    port_links = 0

    for route in routes:
        pieces = _route_axis_pieces(graph, route)
        bore_m = bore_to_mm(route.get("nominal_bore")) / 1000.0 / 2.0
        line = route.get("line_number") or ""
        prev_sink: Any = None
        pts = [(float(p["x"]), float(p["y"]), float(p["z"])) for p in route.get("points") or []]
        for i, (a, b) in enumerate(pieces):
            leng = _dist(a, b)
            if leng < 1e-9:
                continue
            seg = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcPipeSegment",
                name=f"{line}-S{i}",
            )
            if hasattr(seg, "PredefinedType"):
                try:
                    seg.PredefinedType = "RIGIDSEGMENT"
                except Exception:
                    pass
            seg.Description = (
                f"LENGTH_M={leng:.6f};LINE={line};SERVICE={route.get('service') or ''};"
                f"BORE={route.get('nominal_bore') or ''};SPEC={route.get('piping_spec') or ''};"
                f"WP={route.get('work_package') or ''};TESTPACK={route.get('test_pack') or ''};"
                f"BORE={route.get('nominal_bore') or ''};R={bore_m:.5f};"
                f"START={a[0]:.4f},{a[1]:.4f},{a[2]:.4f};END={b[0]:.4f},{b[1]:.4f},{b[2]:.4f}"
            )
            ifcopenshell.api.spatial.assign_container(
                model, relating_structure=default_storey, products=[seg]
            )
            ifcopenshell.api.geometry.edit_object_placement(model, product=seg)
            p1 = model.create_entity("IfcCartesianPoint", Coordinates=(float(a[0]), float(a[1]), float(a[2])))
            p2 = model.create_entity("IfcCartesianPoint", Coordinates=(float(b[0]), float(b[1]), float(b[2])))
            poly = model.create_entity("IfcPolyline", Points=[p1, p2])
            axis_rep = model.create_entity(
                "IfcShapeRepresentation",
                ContextOfItems=axis_ctx,
                RepresentationIdentifier="Axis",
                RepresentationType="Curve3D",
                Items=[poly],
            )
            ifcopenshell.api.geometry.assign_representation(model, product=seg, representation=axis_rep)
            src = ifcopenshell.api.system.add_port(model, element=seg)
            snk = ifcopenshell.api.system.add_port(model, element=seg)
            if hasattr(src, "FlowDirection"):
                src.FlowDirection = "SOURCE"
            if hasattr(snk, "FlowDirection"):
                snk.FlowDirection = "SINK"
            if hasattr(src, "PredefinedType"):
                try:
                    src.PredefinedType = "PIPE"
                    snk.PredefinedType = "PIPE"
                except Exception:
                    pass
            if prev_sink is not None:
                ifcopenshell.api.system.connect_port(model, port1=prev_sink, port2=src)
                port_links += 1
            prev_sink = snk
            segment_count += 1
            total_length += leng

        for i in range(1, len(pts) - 1):
            fit = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcPipeFitting",
                name=f"{line}-ELB{i}",
            )
            fit.Description = f"LINE={line};TYPE=ELBOW;CENTRE={pts[i]}"
            ifcopenshell.api.spatial.assign_container(
                model, relating_structure=default_storey, products=[fit]
            )
            fitting_count += 1

    if output_path is None:
        output_path = Path("output/ifc/model.ifc")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(output_path))

    return ArtefactDescriptor(
        id=_aid("IFC"),
        kind=ArtefactKind.IFC,
        status="ready",
        path=str(output_path),
        related_lines=[str(r.get("line_id")) for r in routes if r.get("line_id")],
        payload={
            "segment_count": segment_count,
            "fitting_count": fitting_count,
            "total_length_m": round(total_length, 3),
            "port_links": port_links,
            "schema": "IFC4",
        },
        message=f"IFC4 written: {segment_count} segments, {fitting_count} fittings, ports={port_links}",
    )


_LENGTH_RE = re.compile(r"LENGTH_M=([0-9.]+)")


def reopen_counts(path: Path) -> dict[str, Any]:
    ifcopenshell = _require_ifcopenshell()
    model = ifcopenshell.open(str(path))
    segs = model.by_type("IfcPipeSegment")
    fits = model.by_type("IfcPipeFitting")
    total_len = 0.0
    for s in segs:
        desc = s.Description or ""
        m = _LENGTH_RE.search(desc)
        if m:
            total_len += float(m.group(1))
    return {
        "IfcPipeSegment": len(segs),
        "IfcPipeFitting": len(fits),
        "total_length_m": round(total_len, 3),
        "axis_length_m": round(axis_length_m(model), 6),
        "port_connections": len(model.by_type("IfcRelConnectsPorts")),
    }


def axis_length_m(model: Any) -> float:
    """Sum IfcPolyline Axis representation lengths (file units = metres)."""
    total = 0.0
    for seg in model.by_type("IfcPipeSegment"):
        shape = getattr(seg, "Representation", None)
        if shape is None:
            continue
        for rep in shape.Representations or []:
            ident = (rep.RepresentationIdentifier or "").upper()
            if ident != "AXIS":
                continue
            for item in rep.Items or []:
                coords: list[tuple[float, ...]] = []
                if item.is_a("IfcPolyline"):
                    coords = [tuple(float(c) for c in p.Coordinates) for p in item.Points]
                elif item.is_a("IfcIndexedPolyCurve"):
                    plist = item.Points
                    raw = getattr(plist, "CoordList", None) or []
                    coords = [tuple(float(c) for c in row) for row in raw]
                for a, b in zip(coords, coords[1:]):
                    if len(a) >= 3 and len(b) >= 3:
                        total += _dist((a[0], a[1], a[2]), (b[0], b[1], b[2]))
    return total


def validate_ifc4(path: Path, *, express_rules: bool = True) -> dict[str, Any]:
    """Run ifcopenshell.validate schema (+ express). Zero errors required for B19."""
    ifcopenshell = _require_ifcopenshell()
    import ifcopenshell.validate

    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(path), logger, express_rules=express_rules)
    statements = list(getattr(logger, "statements", []) or [])
    errors = [
        s
        for s in statements
        if str(s.get("level", "")).lower() in {"error", "critical", "exception"}
        or "error" in str(s.get("message", "")).lower()
    ]
    # json_logger uses attribute-style levels: logger.error(...) → level="error"
    errors = [s for s in statements if str(s.get("level", "")).lower() == "error"] or errors
    return {
        "schema": "IFC4",
        "express_rules": express_rules,
        "n_statements": len(statements),
        "n_errors": len(errors),
        "errors": errors[:12],
    }


def unique_port_pairs(model: Any) -> set[frozenset[int]]:
    pairs: set[frozenset[int]] = set()
    for rel in model.by_type("IfcRelConnectsPorts"):
        a = rel.RelatingPort.id()
        b = rel.RelatedPort.id()
        pairs.add(frozenset((int(a), int(b))))
    return pairs


def route_length_m(routes: list[dict[str, Any]]) -> float:
    total = 0.0
    for route in routes:
        pts = [(float(p["x"]), float(p["y"]), float(p["z"])) for p in route.get("points") or []]
        for a, b in zip(pts, pts[1:]):
            total += _dist(a, b)
    return total
