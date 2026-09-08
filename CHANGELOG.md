# Changelog

## Unreleased (M1 B05–B09 — not v2.0.0)

- B05: vendor all 35 DEXPI 1.3 TrainingTestCases example P&IDs (CC-BY-4.0) with sha manifest + `pins.json`.

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
