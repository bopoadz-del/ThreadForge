# ThreadForge — Hard Walls

Capabilities we **cannot** complete without proprietary licenses, vendor schemas,
live plant credentials, or a CAD kernel. Each wall lists **why** and the
**workaround left in code**.

---

## 1. Vendor DEXPI / Proteus extensions only (public XSD + TrainingTestCases vendored)

| | |
|---|---|
| **Why** | Official vendor extensions (AVEVA / Hexagon / Autodesk) remain license-gated. TrainingTestCases **C08** has no Proteus XML upstream (PDF/XLS only); cross-file OPC joins use C01-derived capability fixtures under `pids/c08/`. |
| **Workaround** | Namespace-aware Proteus/DEXPI parser with GenericAttribute mapping. Public Proteus 4.1 (+4.1.1 RC1) XSD and DEXPI 1.3 C01/C03/E06/P01/P02 under `fixtures/public/dexpi13/` (CC-BY-4.0). `validate_xsd()` by SchemaVersion. OPC cross-sheet via P02. |

## 2. Autodesk ISOGEN PCF **certification** only

| | |
|---|---|
| **Why** | Full certification / material catalogues remain proprietary. |
| **Workaround** | Structurally valid sequential PCF (contiguous PIPE/ELBOW with LR tangents, positioned fittings, MATERIALS). `pcf_reader` enforces contiguity. Not Autodesk-certified. |

## 3. Certified isometric drawings (ISOGEN / vendor iso engines)

| | |
|---|---|
| **Why** | Production stamped isometrics need vendor engines and symbol libraries. |
| **Workaround** | True 30° isometric SVG with dimensions, north arrow, BOM, title block marked **HEURISTIC — NOT FOR CONSTRUCTION**. |

## 4. Proprietary CAD readers (NWD / RVT / DGN / DWG) — IFC4 / DXF supported

| | |
|---|---|
| **Why** | Autodesk Navisworks/Revit, AVEVA, Hexagon, and ODA/Teigha SDKs require commercial licenses. |
| **Workaround** | No NWD/RVT/DGN/DWG ingest (`ifc_in` logs one WALL line and returns empty). **IFC4** out via `ifcopenshell` (`exporters/ifc.py`); **IFC4-in** structure/equipment → AABB/capsule (`exporters/ifc_in.py`); **DXF** via `ezdxf` (`exporters/dxf.py`). |

## 5. Autodesk / AVEVA / HEXAGON live APIs

| | |
|---|---|
| **Why** | Require customer entitlements, network credentials, and plant project databases. |
| **Workaround** | Offline fixtures + local `output/` artefacts. Agent tools never call vendor clouds. |

## 6. Live plant data / credentials

| | |
|---|---|
| **Why** | Real client P&IDs and schedules are confidential. |
| **Workaround** | Invented synthetic tags only. No client data in repo. |

## 7. ~~GPU / CAD kernel collision solids~~ — **REMOVED**

| | |
|---|---|
| **Status** | Overcome with pure math: capsule–capsule / capsule–AABB clash (`clash.py`) and obstacle-aware A* routing (`routing.route_astar`). No B-rep kernel required for pipe-vs-pipe / pipe-vs-box. |

## 8. Web 3D viewer / interactive Gantt UI

| | |
|---|---|
| **Why** | Out of scope (also risks looking like a commercial product clone). |
| **Workaround** | Data + SVG + JSON/CSV exports; FastAPI/MCP tools for agents/CLI only. |

---

When a wall is hit, code returns `status` / `wall` / `limits` fields rather than pretending completeness.
