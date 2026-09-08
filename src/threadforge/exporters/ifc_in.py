"""IFC4 structure/equipment → AABB and capsule obstacles (ifcopenshell).

Reads IfcColumn / IfcBeam / IfcMember / IfcWall / IfcSlab / IfcFooting
and equipment (IfcTank / IfcVessel / IfcPump / IfcBuildingElementProxy / …)
via ObjectPlacement + IfcBoundingBox. Optional ifcopenshell.geom fallback
when a product has no BoundingBox.

NWD / RVT / DGN / DWG are walled — one log line, empty obstacle set.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Union

from threadforge.graph import TopologyGraph
from threadforge.models import DesignVolume, Equipment, Nozzle, Pipeline

logger = logging.getLogger("threadforge.ifc_in")

Point3 = tuple[float, float, float]
AABB = tuple[float, float, float, float, float, float]

WALL_SUFFIXES = {".nwd", ".rvt", ".dgn", ".dwg"}

STRUCTURAL_IFC = (
    "IfcBeam",
    "IfcColumn",
    "IfcMember",
    "IfcWall",
    "IfcWallStandardCase",
    "IfcSlab",
    "IfcFooting",
    "IfcPlate",
    "IfcRailing",
)
EQUIPMENT_IFC = (
    "IfcTank",
    "IfcVessel",
    "IfcPump",
    "IfcCompressor",
    "IfcUnitaryEquipment",
    "IfcBuildingElementProxy",
    "IfcElectricGenerator",
    "IfcEngine",
    "IfcBoiler",
    "IfcChimney",
)

PUBLIC_RACK_IFC = Path(__file__).resolve().parents[3] / "fixtures" / "public" / "ifc" / "pipe_rack.ifc"


def _identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
    return out


def _xform(m: list[list[float]], p: Point3) -> Point3:
    x = m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3]
    y = m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3]
    z = m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3]
    return (x, y, z)


def _cross(a: Point3, b: Point3) -> Point3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v: Point3) -> Point3:
    leng = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    if leng < 1e-18:
        return (0.0, 0.0, 0.0)
    return (v[0] / leng, v[1] / leng, v[2] / leng)


def _axis2_matrix(axis2: Any) -> list[list[float]]:
    loc = tuple(float(c) for c in (axis2.Location.Coordinates if axis2.Location else (0.0, 0.0, 0.0)))
    if len(loc) < 3:
        loc = (loc[0] if loc else 0.0, loc[1] if len(loc) > 1 else 0.0, 0.0)
    z = (0.0, 0.0, 1.0)
    x = (1.0, 0.0, 0.0)
    if getattr(axis2, "Axis", None) is not None and axis2.Axis.DirectionRatios:
        zr = tuple(float(c) for c in axis2.Axis.DirectionRatios)
        z = _norm((zr[0], zr[1] if len(zr) > 1 else 0.0, zr[2] if len(zr) > 2 else 0.0))
    if getattr(axis2, "RefDirection", None) is not None and axis2.RefDirection.DirectionRatios:
        xr = tuple(float(c) for c in axis2.RefDirection.DirectionRatios)
        x = _norm((xr[0], xr[1] if len(xr) > 1 else 0.0, xr[2] if len(xr) > 2 else 0.0))
    y = _norm(_cross(z, x))
    x = _norm(_cross(y, z))
    return [
        [x[0], y[0], z[0], loc[0]],
        [x[1], y[1], z[1], loc[1]],
        [x[2], y[2], z[2], loc[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _world_matrix(placement: Any) -> list[list[float]]:
    if placement is None:
        return _identity()
    parent = _identity()
    rel_to = getattr(placement, "PlacementRelTo", None)
    if rel_to is not None:
        parent = _world_matrix(rel_to)
    rel = getattr(placement, "RelativePlacement", None)
    if rel is None:
        return parent
    return _matmul(parent, _axis2_matrix(rel))


def _iter_boxes(representation: Any) -> list[Any]:
    boxes: list[Any] = []
    if representation is None:
        return boxes
    reps = getattr(representation, "Representations", None) or []
    for rep in reps:
        for item in getattr(rep, "Items", None) or []:
            if item.is_a("IfcBoundingBox"):
                boxes.append(item)
            elif item.is_a("IfcMappedItem"):
                src = getattr(item.MappingSource, "MappedRepresentation", None)
                boxes.extend(_iter_boxes_from_rep(src))
    return boxes


def _iter_boxes_from_rep(rep: Any) -> list[Any]:
    if rep is None:
        return []
    out: list[Any] = []
    for item in getattr(rep, "Items", None) or []:
        if item.is_a("IfcBoundingBox"):
            out.append(item)
    return out


def _bbox_aabb(box: Any, matrix: list[list[float]]) -> AABB:
    corner = tuple(float(c) for c in box.Corner.Coordinates)
    if len(corner) < 3:
        corner = (corner[0] if corner else 0.0, corner[1] if len(corner) > 1 else 0.0, 0.0)
    dx, dy, dz = float(box.XDim), float(box.YDim), float(box.ZDim)
    corners = [
        (corner[0] + ox, corner[1] + oy, corner[2] + oz)
        for ox in (0.0, dx)
        for oy in (0.0, dy)
        for oz in (0.0, dz)
    ]
    world = [_xform(matrix, c) for c in corners]
    xs = [p[0] for p in world]
    ys = [p[1] for p in world]
    zs = [p[2] for p in world]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _geom_aabb(product: Any) -> Optional[AABB]:
    try:
        import ifcopenshell.geom

        settings = ifcopenshell.geom.settings()  # type: ignore[no-untyped-call]
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, product)
        geom = getattr(shape, "geometry", None)
        verts = getattr(geom, "verts", None)
        if verts is None or len(verts) < 3:
            return None
        xs = [float(verts[i]) for i in range(0, len(verts), 3)]
        ys = [float(verts[i]) for i in range(1, len(verts), 3)]
        zs = [float(verts[i]) for i in range(2, len(verts), 3)]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
    except Exception:  # noqa: BLE001
        return None


def _product_kind(entity: Any) -> str:
    if entity.is_a() in EQUIPMENT_IFC or any(entity.is_a(k) for k in EQUIPMENT_IFC):
        return "equipment"
    return "structure"


def load_ifc_obstacles(path: Union[str, Path]) -> dict[str, Any]:
    """Parse IFC structure/equipment into AABBs and capsules.

    Measured via ifcopenshell entity iteration + BoundingBox transforms
    (not file-presence). Walled CAD suffixes emit one log line and return empty.
    """
    p = Path(path)
    if p.suffix.lower() in WALL_SUFFIXES:
        logger.warning("WALL: NWD/RVT/DGN/DWG ingest blocked — IFC4 only (%s)", p.name)
        return {
            "aabbs": [],
            "capsules": [],
            "products": [],
            "wall": "cad_reader",
            "path": str(p),
        }
    try:
        import ifcopenshell
    except ImportError as exc:
        raise ImportError("ifcopenshell is required for IFC-in — pip install 'threadforge[ifc]'") from exc

    model = ifcopenshell.open(str(p))
    wanted = STRUCTURAL_IFC + EQUIPMENT_IFC
    products: list[dict[str, Any]] = []
    aabbs: list[AABB] = []
    capsules: list[dict[str, Any]] = []
    for ifc_class in wanted:
        try:
            ents = model.by_type(ifc_class)
        except Exception:  # noqa: BLE001
            continue
        for ent in ents:
            matrix = _world_matrix(getattr(ent, "ObjectPlacement", None))
            boxes = _iter_boxes(getattr(ent, "Representation", None))
            aabb: Optional[AABB] = None
            if boxes:
                aabb = _bbox_aabb(boxes[0], matrix)
            if aabb is None:
                aabb = _geom_aabb(ent)
            if aabb is None:
                continue
            kind = _product_kind(ent)
            rec = {
                "global_id": getattr(ent, "GlobalId", None),
                "name": getattr(ent, "Name", None),
                "ifc_class": ent.is_a(),
                "kind": kind,
                "aabb": aabb,
            }
            products.append(rec)
            aabbs.append(aabb)
            # Capsule along the longest AABB edge (column ≈ vertical, beam ≈ horizontal).
            xmin, ymin, zmin, xmax, ymax, zmax = aabb
            dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
            cx, cy, cz = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0
            if dz >= dx and dz >= dy:
                a, b = (cx, cy, zmin), (cx, cy, zmax)
                radius = max(dx, dy) / 2.0
            elif dx >= dy:
                a, b = (xmin, cy, cz), (xmax, cy, cz)
                radius = max(dy, dz) / 2.0
            else:
                a, b = (cx, ymin, cz), (cx, ymax, cz)
                radius = max(dx, dz) / 2.0
            capsules.append({"a": a, "b": b, "radius": radius, "ifc_class": ent.is_a(), "kind": kind})

    structure = sum(1 for r in products if r["kind"] == "structure")
    equipment = sum(1 for r in products if r["kind"] == "equipment")
    return {
        "aabbs": aabbs,
        "capsules": capsules,
        "products": products,
        "structure_count": structure,
        "equipment_count": equipment,
        "path": str(p),
        "schema": model.schema,
        "wall": None,
    }


def attach_ifc_obstacles(graph: TopologyGraph, path: Union[str, Path]) -> dict[str, Any]:
    """Store IFC obstacles on ``graph.metadata['ifc_obstacles']`` for A* / clash."""
    obs = load_ifc_obstacles(path)
    graph.metadata["ifc_obstacles"] = obs
    return obs


def aabb_penetration_count(
    points: list[Point3],
    aabbs: list[AABB],
    radius: float = 0.0,
    samples: int = 16,
) -> int:
    """Count interior polyline samples that sit inside an AABB expanded by radius."""
    hits = 0
    for a, b in zip(points, points[1:]):
        for i in range(samples + 1):
            t = i / samples
            p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))
            # Endpoints of the whole polyline may sit at nozzles; skip only exact ends later.
            for box in aabbs:
                xmin, ymin, zmin, xmax, ymax, zmax = box
                if (
                    xmin - radius <= p[0] <= xmax + radius
                    and ymin - radius <= p[1] <= ymax + radius
                    and zmin - radius <= p[2] <= zmax + radius
                ):
                    hits += 1
                    break
    return hits


def route_ifc_penetrations(
    routes: list[dict[str, Any]],
    aabbs: list[AABB],
    skip_endpoints: bool = True,
    samples: int = 20,
) -> int:
    """Interior-sample penetration count across routes (0 = clear)."""
    total = 0
    for route in routes:
        pts = [(p["x"], p["y"], p["z"]) for p in route.get("points") or []]
        if len(pts) < 2:
            continue
        start, end = pts[0], pts[-1]
        for a, b in zip(pts, pts[1:]):
            for i in range(samples + 1):
                t = i / samples
                p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))
                if skip_endpoints and (
                    (abs(p[0] - start[0]) + abs(p[1] - start[1]) + abs(p[2] - start[2]) < 1e-6)
                    or (abs(p[0] - end[0]) + abs(p[1] - end[1]) + abs(p[2] - end[2]) < 1e-6)
                ):
                    continue
                for box in aabbs:
                    if box[0] <= p[0] <= box[3] and box[1] <= p[1] <= box[4] and box[2] <= p[2] <= box[5]:
                        total += 1
                        break
    return total


def four_line_ifc_graph() -> TopologyGraph:
    """Four nozzle-anchored lines that must clear the vendored rack IFC."""
    g = TopologyGraph()
    g.volumes["VOL-IFC-RACK"] = DesignVolume(
        id="VOL-IFC-RACK",
        name="IFC rack plot",
        xmin=30.0,
        ymin=35.0,
        zmin=0.0,
        xmax=70.0,
        ymax=55.0,
        zmax=15.0,
    )
    specs = [
        ("L-IFC-P1", "IFC-P1", "PROCESS", (35.0, 42.0, 6.0), (60.0, 42.0, 6.0), '4"'),
        ("L-IFC-P2", "IFC-P2", "PROCESS", (35.0, 43.2, 8.0), (60.0, 43.2, 8.0), '4"'),
        ("L-IFC-U1", "IFC-U1", "UTILITY", (35.0, 42.0, 7.0), (60.0, 42.0, 7.0), '3"'),
        ("L-IFC-D1", "IFC-D1", "DRAIN", (35.0, 43.2, 4.0), (60.0, 43.2, 4.0), '3"'),
    ]
    for i, (lid, lnum, svc, start, end, bore) in enumerate(specs, start=1):
        ea, eb = f"EQ-IFC-{i}A", f"EQ-IFC-{i}B"
        na, nb = f"{ea}-N1", f"{eb}-N1"
        g.equipment[ea] = Equipment(id=ea, tag=ea, nozzles=[na], volume_id="VOL-IFC-RACK")
        g.equipment[eb] = Equipment(id=eb, tag=eb, nozzles=[nb], volume_id="VOL-IFC-RACK")
        g.nozzles[na] = Nozzle(id=na, tag="N1", equipment_id=ea, x=start[0], y=start[1], z=start[2])
        g.nozzles[nb] = Nozzle(id=nb, tag="N1", equipment_id=eb, x=end[0], y=end[1], z=end[2])
        g.pipelines[lid] = Pipeline(
            id=lid,
            line_number=lnum,
            from_tag=na,
            to_tag=nb,
            nominal_bore=bore,
            service=svc,
        )
    return g


def public_rack_path() -> Path:
    return PUBLIC_RACK_IFC
