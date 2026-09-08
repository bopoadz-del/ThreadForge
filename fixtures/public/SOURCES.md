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

Full TrainingTestCases ``dexpi 1.3/example pids/`` XML set (35 files; C08 has 0 upstream XML).
Per-file ingest counts: ``dexpi13/pins.json``. SHA manifest: ``dexpi13/fetch_manifest.json``.

| File | sha256 | bytes |
|---|---|---|
| dexpi13/xsd/ProteusPIDSchema_4.1.xsd | f14652c0f3ff79eea6bb1c92f276c79f41ebad2945324f70b348c377c00385ff | 92156 |
| dexpi13/xsd/ProteusPIDSchema_4.1.1_RC1.xsd | 09864b15ef81dca3334bcdda78088602bf22d9d5c0bb1d2d54b058241b39eecb | 94220 |
| dexpi13/pids/C01V04-VER.EX01.xml | a2b172f04e0dcf9a668e158c6dee3b5fd0dd4e9027b572dc39e54470562b809c | 445726 |
| dexpi13/pids/C02V03-VER.EX02.xml | dfe4323c18d018caa4b28ec789b3dbee21be73c6a07c7cbd0791ceebd322113b | 157666 |
| dexpi13/pids/C03V04-VER.EX02.xml | a1c892f3bc21338c2546baf71e10abf11e3653b7cd6956b1a24bcfab0db88f14 | 68507 |
| dexpi13/pids/E01V02-VER.EX01.xml | 654c73ecd3eff68940bf05f48436d8662652e4faa656c759fb24d458c0e9acfc | 4610 |
| dexpi13/pids/E02V02-VER.EX01.xml | 8bdab30cfa079009975f04d93b087a881473259a6c2e54fab2aefa7003732be6 | 12280 |
| dexpi13/pids/E03V01-VER.EX01.xml | a26bda5dda7d3b8bd6b661a5c2f8803463f94027e97ff142bcd3a0f35b8e1357 | 3113 |
| dexpi13/pids/E04V01-VER.EX01.xml | f40f8618b0f9a4e169bf1c43e93eb14fc478d49cd8607d2aee5452662211dbca | 2728 |
| dexpi13/pids/E05V01-VER.EX01.xml | 4e899b13e7eac2a12994c6e03ff8440e43f7c53297fae4cb9fbe26a93dc6e12c | 3978 |
| dexpi13/pids/E06V01-VER.EX01.xml | 2a6b4762cd1c85c9fcf329f885ca368769a84ebd5dbf5966c6a0781bb4038351 | 6288 |
| dexpi13/pids/E07V01-VER.EX01.xml | 04ba63b74b4d90866e8de32e4b63d1fdba64699e699ef4a0fa018a14ffed77ac | 5175 |
| dexpi13/pids/E08V01-VER.EX01.xml | 942d3e1e16308d926f861b0f7265a1fa8053f9d2c309615d17ef6646659d6d04 | 4263 |
| dexpi13/pids/E09V01-VER.EX01.xml | 861ff607e401ed84f3c9e54fa3ed3985d878fa087c1d50125360573185007f66 | 1367 |
| dexpi13/pids/E11V01-VER.EX01.xml | 0636399a6eb1f6fc1062898de4f163ac9714864481f5b44ebf7fc1235e76850d | 4650 |
| dexpi13/pids/E12V01-VER.EX01.xml | edbe65f609085d7d94b30c83e83a746515a85d813c325cf5508ad6e2c4bed3f6 | 11286 |
| dexpi13/pids/E13V01-VER.EX01.xml | fde56b4547e3b00e46c7b3d82ba0a249b10824cff1f0661a4df6bfaceeefe03d | 2924 |
| dexpi13/pids/E14V01-VER.EX01.xml | 8452c16b9f61cddbba5e94da7e2ee3469a0513957efb6cdda1536873cdb52628 | 3588 |
| dexpi13/pids/I01V01-VER.EX01.xml | fa9a947c0967f0fb9312eb6793354056d4f6b96e6f11425e924a07169d9b9de2 | 4918 |
| dexpi13/pids/I02V01-VER.EX01.xml | b3b8c59b7005e44e57ec56b8df407fed4115ee6411988eed4ba040ea834c291d | 5106 |
| dexpi13/pids/I03V01-VER.EX01.xml | 850f7d12e880b5768622f26b97238e70bb7df4687f3451a359a76124e5358364 | 7212 |
| dexpi13/pids/I04V01-VER.EX01.xml | 91b301bad8f432feb5dfff46190830a9415c63fd9904485a700f9fda7dfc10b5 | 7477 |
| dexpi13/pids/I05V01-VER.EX01.xml | 19cd0e7aef5238af1021d32e24b4cd2e46dd92e960c62727324a19d5384cab76 | 12267 |
| dexpi13/pids/I06V01-VER.EX01.xml | 949b2bcf9bf42b7529171b3f5b3bdd722c5b324640b23ee6af4adc101f2cf79b | 12311 |
| dexpi13/pids/I07V01-VER.EX01.xml | 921f13ffe2f02f50e9b0569085b266eeddbe191244d16f40578fcf65912d5a78 | 9990 |
| dexpi13/pids/I08V01-VER.EX01.xml | f8eea1484780126434fe41cd940aa2685d9d1bd738fda0567ecd4a6e5fda1bac | 13989 |
| dexpi13/pids/I09V01-VER.EX01.xml | b2a4bbf0ea128f7f0a204ae2b2414b168afd103d4cf4a12f4796bef8a600716d | 4134 |
| dexpi13/pids/I10V01-VER.EX01.xml | 3fe1c132d83b4f5d73e109117b2dcf4b37abebd861e1709a6a995548a5c74fd5 | 3560 |
| dexpi13/pids/I11V01-VER.EX01.xml | 4f3b10c9eafe82cfb5806f51ae12e0348a55c09eb171782e5542d34a9b3155a5 | 4308 |
| dexpi13/pids/I12V01-VER.EX01.xml | e6b2cfae50a272d4ad2bf180c147a6f460c47d40f8739246789523d09b246024 | 5122 |
| dexpi13/pids/I13V01-VER.EX01.xml | 20310c5d3cd076de9afa818a59a9ce885e87b5597bea4024e0f64e12bb33da48 | 7321 |
| dexpi13/pids/I14V01-VER.EX01.xml | 5968128b25264d16a50f4a5b670af08edabb2b993207001c919a7b48bc7a1474 | 5847 |
| dexpi13/pids/I15V01-VER.EX01.xml | d588226c734060b5d30dfa6a84ab5e296fa89b749bb41b35c9f9863a57aa2a05 | 6339 |
| dexpi13/pids/P01V01-VER.EX01.xml | 1c88ab8aec8ac9d721b454aa9dc1fe669e6efbea871a36e39beeb9a5fdac4076 | 3684 |
| dexpi13/pids/P02V01-VER.EX01.xml | 6084e2bbaba4f018551f2db6744fba2976b95a15de172e6cf5f342df009f6611 | 4259 |
| dexpi13/pids/P03V01-VER.EX01.xml | 7c5b3ef54e709e5aada7c59599181e56bd64a36f32b9965ef823afa88f0ca52f | 2903 |
| dexpi13/pids/P04V01-VER.EX01.xml | 535a01b3433bdceb0128db8369178c156507ee3d3dbdd9786eae5c30d1c9b543 | 4651 |

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
