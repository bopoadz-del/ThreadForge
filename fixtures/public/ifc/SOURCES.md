# Public IFC fixtures

Offline-first. Generated once via `python scripts/generate_pipe_rack_ifc.py`.

| Asset | Notes |
|---|---|
| `pipe_rack.ifc` | IFC4 pipe rack written with ifcopenshell (IfcColumn ×4, IfcBeam ×3, IfcTank ×1). Each product has an `IfcBoundingBox` so IFC-in does not need a CAD kernel. **Not** a Schependomlaan extract (that model is a multi-MB building); generated so column AABBs are pinned and 4-line routing evidence is deterministic. No client data. |

Schema: IFC4 (buildingSMART). License: generated in-tree for ThreadForge tests.
