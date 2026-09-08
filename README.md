# ThreadForge

**Agent-native EPC piping digital thread** (geometrically correct routes/PCF/clash; externally drivablen via FastAPI/MCP) — P&ID (Proteus/DEXPI-shaped XML) → topology graph → layout / design volumes → piping artefacts → AWP work packages → 4D schedule (co-activity + look-ahead), with maturity gates.

Inspired by public industrial digital-twin UI *patterns* (P&ID selection, Pid-to-3d pipeline, work packages, 4D planning). **Not** a brand or UI clone.

Hard limits (proprietary CAD, full DEXPI XSD, etc.) are documented in **[WALLS.md](WALLS.md)**.

## Architecture

```mermaid
flowchart LR
  subgraph ingest [Upload]
    XML[DEXPI/Proteus XML]
    SVG[SVG optional]
  end
  subgraph topo [Topology]
    G[TopologyGraph]
    T[Tags / Lines / FromTo]
    BL[Battery Limits]
  end
  subgraph layout [Layout]
    DV[Design Volumes]
    WP[Work Packages CWP/IWP]
  end
  subgraph piping [Piping / Outputs]
    GEN[Generators]
    ISO[Isos JSON+SVG]
    PCF[PCF text]
    GA[GA plot SVG]
    QTY[Quantities / CSV]
    TP[Test Packs]
  end
  subgraph fourd [4D / Maturity]
    SCH[Schedule4D]
    CO[Co-activity]
    LA[Look-ahead]
    MAT[Maturity Gates]
  end
  XML --> G
  SVG -.-> G
  G --> T --> BL
  G --> DV --> WP
  T --> GEN --> ISO
  GEN --> PCF
  GEN --> GA
  GEN --> QTY
  G --> TP
  WP --> SCH
  SCH --> CO
  SCH --> LA
  G --> MAT
  Cascade[CascadeEngine] -.dirty.-> GEN
  Cascade -.dirty.-> WP
  Cascade -.dirty.-> TP
```

## Acceptance (AUTO-GENERATED from scripts/acceptance.py)

Do not hand-edit the table below — regenerate via `python scripts/acceptance.py`.

```
A01 PASS status=validated engine=xmlschema errors=0
A02 PASS seg=23 eq=21 nz=21 sized=19 pif=6 dn_ok=True
A03 PASS xmls=2 joins=1 pinned=1
A04 PASS errors=none gaps=6
A05 PASS fabricated_lines=['LINE-120-P-1002'] flagged=2 refuses_ifc=True
A06 PASS mismatches=none lines=4
A07 PASS max_bends=2 clears=True clear_meta=True drains=True
A08 PASS rich_hard=0 crafted_hard=1 excluded_keys=True
A09 PASS supports_per_line={'LINE-200-P-1001': 6, 'LINE-200-P-1002': 15, 'LINE-210-G-2001': 8, 'LINE-200-D-1010': 7} expected={'LINE-200-P-1001': 6, 'LINE-200-P-1002': 15, 'LINE-210-G-2001': 8, 'LINE-200-D-1010': 7} types_ok=True
A10 PASS problems=none files=4
A11 PASS parsed=4
A12 PASS checks=[True, True, True, True, True, True] cited=True keys=[0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
A13 PASS svg30=True bom=True nfc=True
A14 PASS segments=9 fittings=5 pset=True
A15 PASS entities=21 layers=['0', 'Defpoints', 'VOL_VOL-200', 'VOL_VOL-210', 'VOL_VOL-220', 'VOL_VOL-RACK', 'EQP', 'PIP', 'ISO', 'INS'] has_vol=True has_disc=True art=ready
A16 PASS rows=4 keys_ok=True recon=True
A17 PASS packs=6 with_pressure=6 sample={'boundary': ['FlowInPipeOffPageConnector-1', 'Nozzle-1', 'Nozzle-2', 'Nozzle-3', 'Nozzle-4', 'Nozzle-5'], 'test_pressure_barg': 90.0, 'design_pressure_barg': 60.0}
A18 PASS total=30 iwps=23 size_ok=True qty_ok=True crew_ok=True
A19 PASS hard=1 soft=6 keys=['adjacent_count', 'craft_warnings', 'flagged', 'flagged_count', 'hard_count', 'message', 'same_volume_count', 'soft_adjacent']
A20 PASS dirty={'dirty': True, 'change_id': 'CHG-74730fed', 'artefact_kinds': ['routes', 'supports', 'isometric', 'quantities', 'pcf', 'clash', 'ga', 'test_pack', 'work_package'], 'artefact_ids': ['ART-210-G-2001.pcf', 'ART-200-P-1001.pcf', 'ART-200-P-1002.pcf', 'ART-200-D-1010.pcf'], 'affected_wp_ids': [], 'affected_stages': ['topology', 'piping', 'outputs']} line=LINE-200-P-1001
A21 PASS level=L3_60 reasons={'fabricated_count': 0, 'unmatched_opc_count': 0, 'design_pressure_present': False, 'clash_hard': 0, 'factors': ['tags+sheets', 'topology', 'layout+equipment']}
A22 PASS unknown=404 typed=422 first=202 dup=409 openapi=True
A23 PASS common=21 mismatches=none
A24 PASS health=200 tools=401
A25 PASS status=202 body={"id":"job-a39ac9d1f7","job_id":"job-a39ac9d1f7","status":"queued"}
A26 PASS keys=['status', 'fail_closed', 'data_dir_writable', 'registry_schema', 'fixture_shas', 'schema_version']
A27 PASS sha=3482773bee01f95d4014a6f932897805583cefe6 status=healthy
A28 PASS ci_run.json sha=3482773bee01f95d4014a6f932897805583cefe6 conclusion=completed run_id=34170106380
A29 PASS changelog=True regen=True tools_mapped=True
A30 PASS tag=v1.0.1 remote=match
ACCEPTANCE: 30/30 PASS
```

## REAL vs STUB

| Capability | Status | Notes |
|---|---|---|
| DEXPI/Proteus-shaped XML parse | **REAL** | Lite + rich + TrainingTestCases; XSD via xmlschema |
| Topology graph | **REAL** | Tags / lines / from-to / BL |
| A* routing + clash | **REAL** | Capsule math; IFC-in AABB |
| PCF writer | **REAL** | Contiguous PIPE/ELBOW; ISOGEN cert WALL |
| Iso SVG/PDF + GA | **REAL** | 30° heuristic — not ISOGEN stamped |
| Hydrotest B31.3 345.4.2 | **REAL** | Capped by B16.5 Table 2-1.1 |
| AWP IWP release + XER/MSPDI | **REAL** | Vendored MSPDI XSD |
| FastAPI + MCP + Alembic registry | **REAL** | SQLite+Postgres; RBAC 3 roles |
| Vendor DEXPI extensions / live APIs | **WALL** | See WALLS.md |
| Web 3D viewer / Gantt UI | **OUT OF SCOPE** | Data + tools only |

## Package layout

```
threadforge/
  WALLS.md
  README.md  ROADMAP.md  LICENSE
  pyproject.toml  requirements.txt
  src/threadforge/
    models.py  graph.py  ingest_dexpi.py  cascade.py
    generators.py  routing.py  schedule_4d.py  maturity.py
    agent_tools.py  cli.py
  fixtures/          # sample_pid.xml, sample_pid_rich.xml, schedule
  output/            # demo PCF / ISO / GA / routes (generated)
  agent/             # SYSTEM.md, run_repl.py, demo_turns.jsonl
  tests/
  demos/run_demo.py
```

## Install & run

```bash
cd /workspace/threadforge
pip install -e ".[dev]"
pytest -q
python demos/run_demo.py
PYTHONPATH=src python agent/run_repl.py agent/demo_turns.jsonl
# or: threadforge ingest && threadforge query --summary
```

Without editable install:

```bash
pip install -r requirements.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python demos/run_demo.py
```

## Agent tools

| Tool | Purpose |
|---|---|
| `ingest_dexpi` | Parse XML → graph |
| `query_graph` | Tags / neighbors / summary |
| `revise_pid` | Change tag/line → dirty set |
| `cascade_rerun` | Re-generate dirty artefacts |
| `build_test_packs` | System-boundary test packs |
| `build_work_packages` | Volume × discipline WPs |
| `attach_schedule` | Load JSON/CSV schedule |
| `look_ahead` | Window + discipline filter + optional CSV |
| `co_activity_check` | Time ∩ volume clashes + report |
| `maturity_check` | Gate IFC-grade export |
| `run_pipeline_stage` | Run upload…outputs stages |
| `export_artefacts` | Write PCF/ISO/GA/routes under `output/` |
| `dexpi_coverage` | Supported elements vs WALL gaps |

## License

MIT — see `LICENSE`.
