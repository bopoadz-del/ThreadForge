#!/usr/bin/env python3
"""Generate the vendored IFC4 pipe-rack (structure + one equipment AABB).

Public IFC4 schema via ifcopenshell. Not a client model. Not Schependomlaan
(that extract is a multi-MB building); this rack has pinned BoundingBox
geometry so IFC-in / A* evidence is deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "fixtures" / "public" / "ifc" / "pipe_rack.ifc"


def _add_bbox_product(
    model: object,
    ifc_class: str,
    name: str,
    origin: tuple[float, float, float],
    dims: tuple[float, float, float],
    storey: object,
    body_ctx: object,
) -> object:
    import ifcopenshell
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.guid

    assert isinstance(model, ifcopenshell.file)
    loc = model.create_entity("IfcCartesianPoint", Coordinates=origin)
    zdir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    xdir = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    axis2 = model.create_entity("IfcAxis2Placement3D", Location=loc, Axis=zdir, RefDirection=xdir)
    placement = model.create_entity("IfcLocalPlacement", RelativePlacement=axis2)
    corner = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    bbox = model.create_entity("IfcBoundingBox", Corner=corner, XDim=dims[0], YDim=dims[1], ZDim=dims[2])
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Box",
        RepresentationType="BoundingBox",
        Items=[bbox],
    )
    pdef = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ent = ifcopenshell.api.root.create_entity(model, ifc_class=ifc_class, name=name)
    ent.ObjectPlacement = placement
    ent.Representation = pdef
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[ent])
    return ent


def main() -> Path:
    import ifcopenshell
    import ifcopenshell.api.context
    import ifcopenshell.api.root
    import ifcopenshell.api.unit

    model = ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="ThreadForge Pipe Rack")
    ifcopenshell.api.unit.assign_unit(model)
    context = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Box",
        target_view="MODEL_VIEW",
        parent=context,
    )
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="RackSite")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Rack")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="L0")
    import ifcopenshell.api.aggregate

    project = model.by_type("IfcProject")[0]
    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    # Four 1.2 m columns blocking the 4-line corridor (x≈47–51, y≈41–44).
    columns = [
        ("COL-SW", (47.4, 41.4, 0.0)),
        ("COL-NW", (47.4, 42.6, 0.0)),
        ("COL-SE", (50.4, 41.4, 0.0)),
        ("COL-NE", (50.4, 42.6, 0.0)),
    ]
    for name, origin in columns:
        _add_bbox_product(model, "IfcColumn", name, origin, (1.2, 1.2, 8.0), storey, body)

    # Tier beams along +X at rack edges (structure, not in the pipe corridor).
    beams = [
        ("BEAM-S-HIGH", (40.0, 39.6, 9.7), (16.0, 0.3, 0.3)),
        ("BEAM-N-MID", (40.0, 45.1, 6.7), (16.0, 0.3, 0.3)),
        ("BEAM-S-LOW", (40.0, 39.6, 3.7), (16.0, 0.3, 0.3)),
    ]
    for name, origin, dims in beams:
        _add_bbox_product(model, "IfcBeam", name, origin, dims, storey, body)

    _add_bbox_product(model, "IfcTank", "TK-RACK-01", (47.0, 48.0, 0.0), (3.0, 3.0, 4.0), storey, body)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(OUT))
    return OUT


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} bytes={path.stat().st_size}")
