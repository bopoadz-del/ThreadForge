# ThreadForge STEP 0 — Audit Baseline

Recorded 2026-09-07 after `pytest -q` + `python demos/run_demo.py` on the MVP tree.
Offline / read-only inventory. No behaviour changes in this commit beyond `.gitignore`, golden snapshot, and this file.

## Commands

| Command | Result |
|---|---|
| `pytest -q` | **34 passed** in ~0.08s |
| `python demos/run_demo.py` | DEMO COMPLETE; artefacts under `output/` |

## Golden snapshot

`output/` → `tests/golden/baseline/` (19 files):

- `pcf/120-P-1001.pcf`, `120-P-1002.pcf`, `124-LPWP-2505.pcf`
- `iso/*.iso.json`, `*.iso.svg` (3 lines)
- `ga/plot_plan.svg`, `plot_plan.json`
- `routes/routes.json`, `supports/supports.json`
- `qty/quantities.json`, `dlb/deliverables.json`
- `csv/tags.csv`, `lines.csv`
- `schedule/look_ahead.csv`, `co_activity_report.json`

## Existence-only asserts

Definition used: assert lines that only check membership (`in` / `not in`), `len(...) >= 2` (or `>= N`), or `Path(...).exists()` / `.exists()`.

**Count: 54** (of 133 total `assert` lines in `tests/`).

Notable thin exporters (geometry/format correctness missing):

| File | Line | Assert |
|---|---|---|
| `test_exporters.py` | 32 | `len(route["points"]) >= 2` |
| `test_exporters.py` | 33 | `"limits" in route` |
| `test_exporters.py` | 39–41 | `"PIPELINE-REFERENCE"/"END-POINT"/"PIPE" in text` |
| `test_exporters.py` | 45, 55, 57, 69, 84–85 | `.exists()` |
| `test_exporters.py` | 59–60, 65–66 | `"<svg" in` / `"path" in` |
| `test_exporters.py` | 86 | `len(result["artefacts"]) >= 5` |

Full list (54):

```
test_agent_repl.py:8,9,10,17,24
test_agent_tools.py:35
test_cascade.py:32-36,51
test_co_activity.py:21
test_exporters.py:32,33,39,40,41,45,47,55,57,59,60,65,66,69,84,85
test_ingest.py:30,35
test_ingest_rich.py:16,17,19,30,31,33
test_look_ahead.py:22,23,32
test_look_ahead_filters.py:21,22,23,35,37,38,52
test_maturity.py:10,25
test_test_packs.py:14,16,19,20,22
```

(See STEP 0 script output in agent log for full one-line forms.)

## `route_pipeline` silent geometry

Code (`src/threadforge/routing.py`):

```python
if start is None:
    start = (0.0, 0.0, 5.0)
if end is None:
    end = (start[0] + 10.0, start[1] + 5.0, start[2])
```

Plus PCF writer fallback (`generators.write_pcf_text`):

```python
if len(pts) < 2:
    pts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]  # 1 m fabricated pipe at origin
```

### Literal `(0,0,5)` / `+(10,5,0)` fallback

**Does not fire on current fixtures.** Every pipeline endpoint resolves via `nozzle_point` → equipment volume centroid when nozzle XYZ is missing.

### Fabricated / degenerate geometry that *does* fire

| Fixture | Line | Mechanism |
|---|---|---|
| `sample_pid.xml` | **120-P-1002** | N2 & N3 both lack XYZ → same VOL-A centroid → `start==end` → route `pts=1`, `length_m=0` → **PCF emits 1 m pipe at origin (0,0,0)–(1000,0,0) mm** with **no fabricated flag** |
| `sample_pid.xml` | 120-P-1001, 124-LPWP-2505 | All nozzles lack XYZ; coords are **silent volume centroids** (no `geometry_source` / fabricated flag) |
| `sample_pid_rich.xml` | (none degenerate) | Nozzles carry explicit XYZ; routes have real lengths |

Lite nozzle XYZ inventory: all four nozzles `xyz=(None,None,None)`.

## ELBOW END-POINT overlap — `output/pcf/120-P-1001.pcf`

Emitted components (metres after /1000):

| Component | END-POINT A | END-POINT B | CENTRE | Length |
|---|---|---|---|---|
| PIPE 1 | (20, 15, 10) | (60, 15, 10) | — | **40.000 m** |
| PIPE 2 | (60, 15, 10) | (60, 15, 7.5) | — | **2.500 m** |
| ELBOW | (20, 15, 10) | (60, 15, 7.5) | (60, 15, 10) | legs 40.000 + 2.500 m |

**Defect:** ELBOW `END-POINT`s are the far ends of the adjacent legs (prev/nxt), not tangent points. Elbow leg1 == full PIPE1; elbow leg2 == full PIPE2.

**Overlap length = 42.500 m** (100 % of both pipes). Real PCF requires PIPE to stop at elbow tangent and ELBOW END-POINTs = those tangents.

Also: `ISOGEN-FILES ISOGEN.FLS` references a missing file; valves/flanges/gaskets/reducers appear only as `MATERIALS-LIST` comments, never as positioned components.

## Init notes

- `git init` performed; `.gitignore` excludes `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, `output/**` (keeps `.gitkeep` structure).
- Removed `src/threadforge.egg-info/` from tree (was present, untracked).
- Venv: `/workspace/threadforge/.venv` with `pip install -e ".[dev]"`.

## Next

D1→D11 per TARGET (valid PCF, no silent geometry, A*, clash, IFC/DXF, DEXPI public, tables, AWP depth, true iso, FastAPI+MCP+SQLite, CI/honesty).


---

## H0 acceptance baseline (v1.0 TARGET)

Recorded after gate green + `scripts/acceptance.py` introduced.
Only **A01** is expected PASS (xmlschema XSD path). All other A## must FAIL until their DO lands.

### Gate

```
ruff check src tests scripts
mypy --strict src
pytest -q
```

All three green (97 pytest).

### Acceptance table

```
A01 PASS status=validated engine=xmlschema errors=0
A02 FAIL seg=23 eq=21 nz=21 sized=0 pif=6 dn_ok=True
A03 FAIL exception: ImportError: cannot import name 'load_fixtures_multi' from 'threadforge.ingest_dexpi' (/workspace/threadforge/src/threadforge/ingest_dexpi.py)
A04 FAIL exception: ImportError: cannot import name 'load_fixtures_multi' from 'threadforge.ingest_dexpi' (/workspace/threadforge/src/threadforge/ingest_dexpi.py)
A05 FAIL exception: TypeError: generate_pcf() missing 1 required positional argument: 'line_id'
A06 FAIL mismatches=['LINE-200-P-1001:route=12.0000 pcf=12.073858347057703', 'LINE-200-P-1002:route=47.5000 pcf=47.37123889803847', 'LINE-210-G-2001:route=22.0000 pcf=21.935619449019235'] lines=4
A07 FAIL max_bends=2 clears=True clear_meta=False drains=False
A08 FAIL exception: AttributeError: 'ArtefactDescriptor' object has no attribute 'get'
A09 FAIL supports_per_line={'LINE-200-P-1001': 6, 'LINE-200-P-1002': 15, 'LINE-210-G-2001': 8, 'LINE-200-D-1010': 7} expected={'LINE-200-P-1001': 6, 'LINE-200-P-1002': 15, 'LINE-210-G-2001': 8, 'LINE-200-D-1010': 7} types_ok=False
A10 FAIL exception: TypeError: generate_pcf() missing 1 required positional argument: 'line_id'
A11 FAIL pcf_strict module missing
A12 FAIL checks=[True, True, False, False, False, False] cited=False keys=[0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0]
A13 FAIL exception: TypeError: generate_isometric() missing 1 required positional argument: 'line_id'
A14 FAIL exception: TypeError: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'ArtefactDescriptor'
A15 FAIL entities=21 layers=['0', 'Defpoints', 'VOL_VOL-200', 'VOL_VOL-210', 'VOL_VOL-220', 'VOL_VOL-RACK', 'EQP', 'PIP'] has_vol=True has_disc=True
A16 FAIL rows=4 keys_ok=False recon=False
A17 FAIL packs=0 has_pressure_meta=False
A18 FAIL total=6 iwps=0 size_ok=False
A19 FAIL exception: AttributeError: 'Schedule4D' object has no attribute 'load'
A20 FAIL dirty=[] line=LINE-200-P-1001
A21 FAIL level={'maturity': 'L3_60', 'factors': ['tags+sheets', 'topology', 'layout+equipment'], 'summary': {'tag_count': 38, 'pipeline_count': 4, 'from_to_count': 10, 'matched_joins': 10, 'unmatched_joins': 0, 'unmatched_tags': [], 'battery_limit_count': 3, 'sheet_count': 3, 'equipment_count': 4, 'volume_count': 4, 'system_count': 2, 'work_package_count': 0}, 'target': None} reasons=None
A22 FAIL bad_status=404 openapi_committed=False
A23 FAIL mcp_server.py missing
A24 FAIL health=200 tools=200
A25 FAIL status=404 body={"detail":"Not Found"}
A26 FAIL keys=['status']
A27 FAIL missing=['Dockerfile', 'render.yaml', 'docker-compose.yml', 'release_gate.py']
A28 FAIL ci_missing=['acceptance.py']
A29 FAIL changelog=False regen=False tools_mapped=False
A30 FAIL tags=[] has_v1=False
ACCEPTANCE: 1/30 PASS
```

C08 note: TrainingTestCases C08 (Covestro) still ships PDF/XLS only — 0 Proteus XML via GitLab API recursive tree. A03/A04 remain red until H1 vendors/joins.

