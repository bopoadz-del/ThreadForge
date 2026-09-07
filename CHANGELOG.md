# Changelog

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
