# Public DEXPI / Proteus fixtures

Offline-first: runtime never fetches. Vendoring happens once via
`make fetch-fixtures` (or `scripts/fetch_public_fixtures.py`).

Vendored tree: `fixtures/public/dexpi13/`

## Targets

| Asset | URL | Notes |
|---|---|---|
| Proteus PID Schema 4.1 XSD | https://raw.githubusercontent.com/ProteusXML/proteusxml/master/ProteusPIDSchema%204.1.xsd | 92156 B |
| Proteus PID Schema 4.1.1 RC1 XSD | https://raw.githubusercontent.com/ProteusXML/proteusxml/master/ProteusPIDSchema%204.1.1%20release%20candidate%201.xsd | optional RC |
| DEXPI TrainingTestCases | https://gitlab.com/dexpi/TrainingTestCases | CC-BY-4.0 — dexpi 1.3 example P&IDs |
| DEXPI specification | https://dexpi.org | Spec PDFs — do not invent XSD content |

## License

- ProteusSchema (GitHub ProteusXML/proteusxml): see upstream README/LICENSE.
- DEXPI TrainingTestCases: **CC-BY-4.0** — full text vendored at `dexpi13/LICENSE`.

## Pinned checksums (sha256)

| File | sha256 | bytes |
|---|---|---|
| dexpi13/xsd/ProteusPIDSchema_4.1.xsd | f14652c0f3ff79eea6bb1c92f276c79f41ebad2945324f70b348c377c00385ff | 92156 |
| dexpi13/xsd/ProteusPIDSchema_4.1.1_RC1.xsd | 09864b15ef81dca3334bcdda78088602bf22d9d5c0bb1d2d54b058241b39eecb | 94220 |
| dexpi13/pids/C01V04-VER.EX01.xml | a2b172f04e0dcf9a668e158c6dee3b5fd0dd4e9027b572dc39e54470562b809c | 445726 |
| dexpi13/pids/C03V04-VER.EX02.xml | a1c892f3bc21338c2546baf71e10abf11e3653b7cd6956b1a24bcfab0db88f14 | 68507 |
| dexpi13/pids/E06V01-VER.EX01.xml | 2a6b4762cd1c85c9fcf329f885ca368769a84ebd5dbf5966c6a0781bb4038351 | 6288 |
| dexpi13/pids/P01V01-VER.EX01.xml | 1c88ab8aec8ac9d721b454aa9dc1fe669e6efbea871a36e39beeb9a5fdac4076 | 3684 |
| dexpi13/pids/P02V01-VER.EX01.xml | 6084e2bbaba4f018551f2db6744fba2976b95a15de172e6cf5f342df009f6611 | 4259 |

## C08 cross-page OPC

TrainingTestCases **C08** (Covestro two connected P&IDs) ships **PDF/XLS only** —
GitLab recursive tree returns **0** Proteus XML. `scripts/fetch_public_fixtures.py`
lists the directory and vendors any future `*.xml`.

Capability fixtures under `dexpi13/pids/c08/` reuse public **C01** FlowOut/FlowIn
OPC element XML (CC-BY-4.0) with shared `CrossPageConnectionAssignmentClass` so
cross-file OPC → FromTo joins are pinned. Not a claim that Covestro UER drawings
were converted.

## Local project fixtures (non-DEXPI-public)

- `fixtures/sample_pid.xml` (lite demo)
- `fixtures/sample_pid_rich.xml` (rich Proteus-shaped)

## C01 pinned topology (after GenericAttribute mapping)

- PipingNetworkSegment: **23**
- Equipment: **21**
- Nozzle: **21** (19 under Equipment + 2 ShapeCatalogue templates)
- ProcessInstrumentationFunction: **6**

| dexpi13/pids/c08/C08_sheet_A.xml | dd4e87578eb214406e6f69fa26a43a067c568426def14be2ed5f353ce8f62cd6 | (C01 OPC-derived) |
| dexpi13/pids/c08/C08_sheet_B.xml | 5311554831d7dc1c287630a2ee12ae109731bc56c0faccc867d8d0e12c7488cf | (C01 OPC-derived) |
