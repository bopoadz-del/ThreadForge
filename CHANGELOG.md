# Changelog

## Unreleased (M3 B16–B21 — not v2.0.0)

- B16: shop-spool PCF split ≤12 m / ≤2 t / ISO 668 1AA 12.0×2.4×2.4 m envelope; field welds `W-<line>-<n>`; `SPOOL-IDENTIFIER`; rich pins.
- B17: one 30° iso SVG sheet per spool (n/N, weld symbols, spool tag, cut lengths, BOM); dim_sum = spool developed length.
- B18: iso + GA PDF via reportlab; page count = sheet count; pypdf extractable line number + NOT FOR CONSTRUCTION.
- B19: IFC4 Axis polyline + IfcRelConnectsPorts; ifcopenshell.validate schema+express 0 errors; axis vs route ±0.5%.
- B20: weld map / NDT schedule — B31.3 341.4.1 Normal Fluid Service 5% RT; .csv + .xlsx; counts = B16.
- B21: MTO per spool / line / IWP / WP; pipe m+kg, fittings, flanges/bolts/gaskets, MSS supports, paint/insulation m²; ±0.1%.

## Unreleased (M2 B10–B15 — not v2.0.0)

- B10: `exporters/ifc_in.py` reads IFC4 structure/equipment → AABB/capsule; vendored ifcopenshell rack; 4 lines A* with zero penetration.
- B11: rack tier table (process high / utility mid / drains low) in `docs/rack_tiers.md`; A* preferred Z; rich pin; no capsule overlap.
- B12: MSS SP-58 kinematic supports (Type 40 anchor, 42 guide, 1 shoe, 51 spring hanger); pinned on rich fixture.
- B13: ASME B31.3 §319.4.1 flexibility screen (SI K=208000; Y from Table C-1); U-loop heuristic on crafted 200 °C line.
- B14: clash categories pipe-vs-structure, insulation OD, 600 mm valve-handwheel hemisphere (PIP PNF0200); rich+IFC hard 0.
- B15: hypothesis properties — A* never penetrates random AABBs; `segment_distance` symmetric, ≥0, brute-sample ±1 mm.

## Unreleased (M1 B05–B09 — not v2.0.0)

- B05: vendor all 35 DEXPI 1.3 TrainingTestCases example P&IDs (CC-BY-4.0) with sha manifest + `pins.json`.
- B06: every vendor PID validates via xmlschema against SchemaVersion-matched XSD; `known_deltas` only per file.
- B07: `DEXPI_COVERAGE_GAPS == []`; 1.3 core parsed; remaining items in `VENDOR_ONLY_GAPS` with vendor names.
- B08: tees/crosses → branched graph; C03 Equinor branch count pinned; branch routes start at tee stub.
- B09: line/valve/instrument/tie-in `.xlsx` (openpyxl); C01 row counts pinned; columns in `docs/exports.md`.

## Unreleased (M0 / K6 — not v2.0.0)

- K6 standing gate: `dump_openapi.py` + `diff` + `mutation_probes.py` (killed-mutation, not no-ops).
- B01: `main` is the only origin head; tags v1.0.0 / v1.0.1 must sit on it (owner-gated collapse documented).
- B02 / A28: HEAD^ Actions `conclusion == "success"` with jobs `test`, `docker`, `acceptance`, `probes`, `publish`; token/network absent → FAIL.
- B03 / A27: `docker_health.json` for HEAD^ must carry health_status 200, health_body, tools_unauth 401, tools_auth 200, image_digest `sha256:…`.
- CI jobs `probes` and `publish` (GHCR) added so B02's job list is honest.

## v1.0.1 — 2026-09-07

- K1: Docker CI job writes `artifacts/ci/docker_health.json`; A27 requires that committed file and HEAD evidence must name the parent sha.
- K2: Acceptance CI job; A28 reads GitHub Actions API or committed `artifacts/ci/ci_run.json` (no fabricated evidence).
- K3: A30 requires `v1.0.1` locally and on origin at the same peeled commit sha (no CHANGELOG fallback); `release_gate.py --tag` refuses unless A01–A29 PASS.
- K4: A22 unknown 404 / typed 422 / dup job 409; A23 MCP vs HTTP export hash parity.
- K5: Version bump to 1.0.1; A27/A28/A30 asserted → measured from real CI artifacts; `make release` tags and pushes `v1.0.1`.

## v1.0.0 — 2026-09-07

- Acceptance harness `scripts/acceptance.py` (A01–A30) gates the release.
- DEXPI public fixtures + xmlschema XSD path; C08 cross-file OPC joins.
- Nozzle tag/size/drawing_xy; B16.5 Table 8 flanges; independent `pcf_strict`.
- Iso 30° / IFC Psets / DXF layers; CWA→CWP→IWP; test-pack pressures.
- FastAPI bearer auth, jobs worker, MCP stdio, Docker/Render/compose, CI acceptance.
