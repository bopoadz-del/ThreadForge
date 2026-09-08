# ThreadForge exports

## Line / valve / instrument / tie-in lists (`.xlsx`)

Produced by `threadforge.exporters.xlsx.export_lists_xlsx` from the topology graph
(openpyxl). Default artefact path: `output/xlsx/lists.xlsx`.

Four sheets. Header row is the column contract below. Row counts for TrainingTestCases
**C01** are pinned in `fixtures/public/dexpi13/pins.json` under `counts.C01V04-VER.EX01.xml.xlsx`.

### `lines`

| Column | Source |
|---|---|
| `line_id` | Pipeline.id (PipingNetworkSegment ID) |
| `line_number` | LineNumberAssignmentClass / LineNumber |
| `from_tag` | Connection FromID |
| `to_tag` | Connection ToID |
| `nominal_bore` | DN GenericAttribute / NominalBore |
| `service` | FluidCode / Service |
| `piping_class` | PipingClassCodeAssignmentClass |
| `fluid_code` | FluidCodeAssignmentClass |
| `insulation` | InsulationTypeAssignmentClass / InsulationThickness |
| `tracing` | HeatTracingTypeRepresentationAssignmentClass |
| `sheet_id` | SheetID when present |

### `valves`

Instance `PipingComponent` rows whose `ComponentClass` contains `Valve` (ShapeCatalogue templates excluded).

| Column | Source |
|---|---|
| `tag` | TagName / component ID |
| `component_class` | ComponentClass (BallValve, GlobeValve, …) |
| `line_id` | Parent PipingNetworkSegment ID |
| `nominal_bore` | NominalDiameterRepresentationAssignmentClass |
| `sheet_id` | SheetID when present |

### `instruments`

| Column | Source |
|---|---|
| `tag` | Instrument tag |
| `instrument_type` | Type / ComponentClass |
| `connected_to` | ConnectedTo / Connection |
| `sheet_id` | SheetID when present |
| `loop_id` | InstrumentationLoopFunction number when associated |

### `tie_ins`

Off-page connectors plus battery limits.

| Column | Source |
|---|---|
| `tag` | OPC TagName or battery-limit TagID |
| `kind` | `opc` \| `battery_limit` |
| `line_id` | Related line when annotated |
| `sheet_id` | SheetID when present |

## Shop spools / welds / NDT / MTO

### Spool PCF (`SPOOL-IDENTIFIER`, `WELD`)

Shop limits (not a piping-code stress rule): developed length ≤ 12.0 m; mass ≤ 2.0 t
from ASME B36.10M kg/m (ρ = 7850 kg/m³); AABB extents fit ISO 668:2020 Table 1
type 1AA shop box 12.0 × 2.4 × 2.4 m. Field welds at breaks; shop BW at metal
joints. IDs: `S-<line_number>-<nn>`, `W-<line_number>-<n>`.

Rich-fixture pins (A* + those limits):

| Line | spools | welds | field | shop |
|---|---|---|---|---|
| LINE-200-P-1001 | 2 | 7 | 1 | 6 |
| LINE-200-P-1002 | 5 | 12 | 4 | 8 |
| LINE-210-G-2001 | 2 | 5 | 1 | 4 |
| LINE-200-D-1010 | 2 | 1 | 1 | 0 |

### Weld / NDT (`.csv` / `.xlsx` sheet `weld_ndt`)

| Column | Source |
|---|---|
| `weld_id` | `W-<line>-<n>` |
| `shop_field` | `shop` \| `field` |
| `weld_type` | `BW` (circumferential butt) |
| `nominal_bore` / `wall_mm` | line NPS; B36.10 wall |
| `vt_pct` | 100 — B31.3 341.4.1(a) |
| `rt_pct` | 5 — B31.3 341.4.1(b)(1) Normal Fluid Service |
| `rt_selected` | first `ceil(0.05×n)` (field then shop) |
| `citation` | ASME B31.3 paragraph 341.4.1 |

### MTO (`output/mto/mto.json`)

Levels: spool → line → IWP → WP. Fields: `pipe_m`, `pipe_kg` (B36.10),
`fittings_count`, `flanges`, `bolts`, `gaskets` (B16.5), `supports` by MSS
SP-58 type, `paint_m2`, `insulation_m2`. Three-level totals must agree ±0.1%.

### PDF

Iso: one page per spool sheet. GA: one page. Extractable text (pypdf) includes
the line number and `HEURISTIC — NOT FOR CONSTRUCTION`.
