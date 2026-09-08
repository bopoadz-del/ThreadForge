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

---

## v1.0.0 → v1.0.1 (A27 / A28 / A30 asserted → measured)

Recorded 2026-09-07 on TARGET v1.0.1. Evidence files are real CI artifacts (not fabricated).
A27/A28 name HEAD's parent sha (`3482773bee01f95d4014a6f932897805583cefe6`).

| Check | v1.0.0 (asserted) | v1.0.1 (measured) |
|---|---|---|
| A27 docker health | files exist (`Dockerfile`, compose, `release_gate.py`) | `artifacts/ci/docker_health.json` from Actions run 34170106380 docker job; `sha=3482773bee01f95d4014a6f932897805583cefe6` `status=healthy` |
| A28 CI run | `acceptance.py` present | `artifacts/ci/ci_run.json` from Actions run [34170106380](https://github.com/bopoadz-del/ThreadForge/actions/runs/34170106380); `status=completed`; jobs test=success docker=success (acceptance failed on parent for missing evidence/tag — bootstrap) |
| A30 release tag | changelog / any v1 tag | `tag=v1.0.1` local+remote peeled sha match (measured after `make release` / tag push) |

---

## v2.0.0 M0 — B01–B40 measured on v1.0.1 tip

Recorded 2026-09-08 on checkout `0005ae911183282079f7027e7877e5da060df0e1` (`v1.0.1^{commit}`).
New harness (`scripts/acceptance.py` B01–B40 / rewritten A27–A28) was run **against that tip** before M0 commits.
HEAD^ at measurement = `3482773bee01f95d4014a6f932897805583cefe6`.
Do not invent evidence. B01–B03 are specified in M0; B04–B40 are M1–M7 and have no PASS path yet.

### B01 owner-gated GitHub steps

Measured via GitHub API: repository `default_branch` is already `main`.
`git ls-remote --heads origin` at v1.0.1 tip returned **4** refs (B01 FAIL).

To make B01 PASS (fast-forward only; **no merge commit on main**):

1. Fast-forward `main` to the M0 tip: `git push origin <m0-sha>:main` (FF-only).
2. Delete every other head: `master`, leftover `cursor/*` agent branches.
3. Re-measure: `git ls-remote --heads origin` must print exactly `refs/heads/main`.
4. Tags `v1.0.0` and `v1.0.1` must be ancestors of that `main` tip. Do **not** tag `v2.0.0` in M0.
5. If GitHub refuses to delete `master` because UI still treats it as default, owner must switch
   **Settings → General → Default branch → main** first, then delete `master`.

### New checks vs v1.0.1 tip (must FAIL)

| Check | Result | Measured reason |
|---|---|---|
| B01 | **FAIL** | `git ls-remote --heads origin` count=4: `cursor/k5-v101-release-f33a`, `cursor/land-full-sot-k1-k4-6685`, `main`, `master` — want `[refs/heads/main]` |
| B02 (no token) | **FAIL** | `token absent` (never PASS without token/network) |
| B02 (token present) | **FAIL** | HEAD^ `3482773bee01f95d4014a6f932897805583cefe6` Actions runs n=3; e.g. run 34170107971 `conclusion=failure` jobs `{acceptance:failure, docker:success, test:success}` missing=`acceptance,probes,publish` |
| B03 / A27 | **FAIL** | `artifacts/ci/docker_health.json` names parent sha but `health_status=None` `health_body=no` `tools_unauth_status=None` `tools_auth_status=None` `image_digest=-` (old `{status:healthy}` only) |
| A28 | **FAIL** | same as B02 (`token absent` without `GITHUB_TOKEN`/`GH_TOKEN`) |

### B01–B40 table (v1.0.1 tip)

| ID | Result | Reason |
|---|---|---|
| B01 | FAIL | heads=4 (main, master, 2× cursor/*); want only `refs/heads/main` |
| B02 | FAIL | token absent, or with token: HEAD^ CI missing `probes`/`publish` and `acceptance≠success` |
| B03 | FAIL | docker_health.json lacks health_status=200, health_body, tools_unauth=401, tools_auth=200, image_digest sha256:… |
| B04 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B05 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B06 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B07 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B08 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B09 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B10 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B11 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B12 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B13 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B14 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B15 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B16 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B17 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B18 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B19 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B20 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B21 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B22 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B23 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B24 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B25 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B26 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B27 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B28 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B29 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B30 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B31 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B32 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B33 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B34 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B35 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B36 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B37 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B38 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B39 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |
| B40 | FAIL | not in M0; M1–M7 not started; evidence_files=0 |

**ACCEPTANCE: 0/40 PASS** on v1.0.1 tip (new B-lines). A01–A26 and A29–A30 still PASS; rewritten A27/A28 FAIL as above (28/30 A-lines).

Walls (NWD/RVT/DGN/DWG, vendor live APIs, ISOGEN cert, client data, web UI): not hit in M0.

### After M0 land (not the v1.0.1-tip row)

Measured after FF `main` → `08f377f08feca30b34cfcf359d2b151a7296c107` and deleting every other origin head:

| Check | Result | Measured |
|---|---|---|
| B01 | **PASS** | `git ls-remote --heads origin` = `refs/heads/main` only; tags v1.0.0=`cffd5b7661b4`, v1.0.1=`0005ae911183` ancestors; v2.0.0 absent |
| B02 | **FAIL** | HEAD^ CI for `08f377f` run [34173455197](https://github.com/bopoadz-del/ThreadForge/actions/runs/34173455197) `conclusion=failure` (acceptance red on B04–B40 / rewritten A27–A28). Jobs test/docker/probes/publish=success; acceptance=failure. Token-absent still FAIL. |
| B03 | evidence committed below | `docker_health.json` from that run’s docker job (sha=`08f377f…`, health_status=200, health_body from live `/health`, tools 401/200, image_digest `sha256:35bd647d…`). PASSes only on the commit whose `HEAD^` is `08f377f`. |

### M1 — B05–B09 measured (DEXPI ceiling)

Recorded 2026-09-08 after standing gate green + `python scripts/acceptance.py` on this M1 tip.
Checks PASS only on computed ingest / xmlschema / row counts (not file presence).
B04 and B10–B40 remain FAIL. Walls untouched. No `v2.0.0` tag.

| ID | Result | Measured |
|---|---|---|
| B05 | **PASS** | 35 TrainingTestCases `dexpi 1.3/example pids/*.xml` (C08 upstream xml=0) ingest with 0 exceptions; sha+counts match `pins.json` |
| B06 | **PASS** | 35/35 `validate_xsd` engine=xmlschema status=validated errors=0; `known_deltas.json` empty (no per-file deltas) |
| B07 | **PASS** | `DEXPI_COVERAGE_GAPS==[]`; C01 tees=5 loops=4 signals=6 acts=3 inline=3; C03 insulation=8 tracing=8; `VENDOR_ONLY_GAPS` = AVEVA/Hexagon/Autodesk dictionaries |
| B08 | **PASS** | C03 Equinor `branch_count=0` (pinned); C01 `branch_count=5`; 5 branch routes start at tee stub XYZ, not a nozzle |
| B09 | **PASS** | C01 xlsx data rows lines=23 valves=11 instruments=6 tie_ins=4 (openpyxl read-back); columns in `docs/exports.md` |

B10–B40: still `_b_unstarted` FAIL (`evidence_files=0`).

**ACCEPTANCE: 6/40 PASS** on M1 tip when B01 is green and B02/B03 have token+HEAD^ evidence; locally without token: B05–B09 PASS, B01 PASS, B02/B03 FAIL (token/parent sha).

---

## M2 — B10–B15 measured (geometry ceiling)

Recorded 2026-09-08 after standing gate green + `python scripts/acceptance.py` on this M2 tip
(started from M1 `e87249ea09ededcfb7cad9d0a6315c70f05fd8f0`).
Checks PASS only on computed IFC entity AABBs, A* sample penetration, rack Z medians,
MSS type counts, B31.3 319.4.1 ratio, clash category counts, and a pytest subprocess
(hypothesis). No file-presence PASS path. B04 and B16–B40 remain FAIL. B02 stays red
(token/HEAD^ CI). No `v2.0.0` tag. Walls: NWD/RVT/DGN/DWG still blocked (`ifc_in` one
WALL log line + empty set); vendor live APIs / ISOGEN cert / client data / web UI untouched.

| ID | Result | Measured |
|---|---|---|
| B10 | **PASS** | ifcopenshell IFC-in: 7 structure + 1 equipment AABB from vendored IFC4 rack; 4 A* lines; interior sample penetrations=0 |
| B11 | **PASS** | rich service→tier pin `{P-1001,P-1002,G-2001=high, D-1010=low}`; crafted rack median Z 10.0 > 7.0 > 4.0; hard=0; min capsule sep=2.000 m |
| B12 | **PASS** | MSS SP-58 Type 40/42/1/51; rich pins P-1001 2/1/0/0, P-1002 2/5/0/1 (6.5 m riser), G-2001 2/2/0/0, D-1010 2/2/0/0; crafted shoe≥1 and spring≥1 |
| B13 | **PASS** | 4 rich lines `no_design_temp`; crafted 200 °C 6″ × 10 m `needs_analysis` Y=21.12 mm (Table C-1 ε=2.112 mm/m × U); U-loop P=0.5 m proposed_ratio=3554.5 ≤ 208000 |
| B14 | **PASS** | rich+IFC hard=0; crafted hard_by_category structure=1 insulation=1 access=1; hemisphere 0.6 m (PIP PNF0200) |
| B15 | **PASS** | `pytest tests/test_hypothesis_geom.py` subprocess rc=0 passed=3 (A* vs random AABB; segment_distance symmetric/≥0/brute ±1 mm) |

B04, B16–B40: still `_b_unstarted` FAIL (`evidence_files=0`).

**ACCEPTANCE: 12/40 PASS** locally (B01 + B05–B15) without token (B02/B03 FAIL token/parent sha).
With token + green HEAD^ jobs, B03 still needs docker_health named for that parent; B02 stays red until later.

---

## M3 — B16–B21 measured (piping outputs)

Recorded 2026-09-08 after standing gate green + `python scripts/acceptance.py` on this M3 tip
(started from M2 `a946a4fc8f4c8453df5139327ab71f00f0a5808c`).
Checks PASS only on computed spool lengths/masses/AABB, iso `dim_sum_mm`,
pypdf page/text, ifcopenshell.validate error count, axis length, unique
IfcRelConnectsPorts pairs, NDT ceil(5%), and MTO three-level relative error.
No file-presence PASS path. B04 and B22–B40 remain FAIL. B02 stays red
(token/HEAD^ CI). No `v2.0.0` tag. Walls: ISOGEN certification — one WALL log
line in `spooling.py`; NWD/RVT/DGN/DWG, vendor live APIs, client data, web UI
untouched.

| ID | Result | Measured |
|---|---|---|
| B16 | **PASS** | Crafted 6″×30 m → 12+12+6 m, 2 field welds `W-CRAFT-30M-1/2`; U-envelope 2 spools; NPS 24 Sch40 (B36.10 OD 610 / t 17.48, 255.425 kg/m) × 10 m splits on 2 t. Rich pins P-1001 2/7/1/6, P-1002 5/12/4/8, G-2001 2/5/1/4, D-1010 2/1/1/0. Limits: 12.0 m / 2000 kg / ISO 668 Table 1 1AA shop box 12.0×2.4×2.4 m |
| B17 | **PASS** | Crafted 30 m → 3 sheets; each `dim_sum_mm == round(spool.length_m×1000)`; n/N, spool tag, cut lengths, BOM, field-weld ids on sheets 1–2 |
| B18 | **PASS** | reportlab iso PDF pages=3=sheet count; GA PDF pages=1; pypdf text contains `CRAFT-30M` and `HEURISTIC — NOT FOR CONSTRUCTION` |
| B19 | **PASS** | ifcopenshell.validate schema+express errors=0; axis=30.000000 route=30.000000; unique IfcRelConnectsPorts pairs=2 for 3 segments |
| B20 | **PASS** | B31.3 341.4.1 Normal Fluid Service 5% RT (ceil → 1 of 2 BW); csv=2 xlsx=2; map count == B16 weld_count=2; 6″ Sch40 wall 7.11 mm |
| B21 | **PASS** | Crafted pipe_m=30.0; rich three-level spool↔line↔IWP/WP rel err 0.000000 (≤0.1%); keys pipe_m/kg, fittings, flanges/bolts/gaskets, supports, paint/insulation m² |

B04, B22–B40: still `_b_unstarted` FAIL (`evidence_files=0`).

**ACCEPTANCE: 18/40 PASS** locally (B01 + B05–B21) without token (B02/B03 FAIL token/parent sha).

