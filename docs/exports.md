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
