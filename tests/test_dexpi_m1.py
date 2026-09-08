"""M1 B05–B09: full TrainingTestCases vendor set, XSD, coverage, branches, xlsx."""

from __future__ import annotations

from pathlib import Path

from threadforge.dexpi_public import (
    entity_counts,
    file_sha256,
    load_pins,
    vendor_xmls,
)
from threadforge.ingest_dexpi import parse_dexpi_xml

ROOT = Path(__file__).resolve().parents[1]
DEXPI13 = ROOT / "fixtures" / "public" / "dexpi13"


def test_b05_vendor_xmls_ingest_and_match_pins():
    xmls = vendor_xmls()
    pins = load_pins()["counts"]
    assert len(xmls) == len(pins) == 35
    exceptions: list[str] = []
    mismatches: list[str] = []
    for path in xmls:
        try:
            graph = parse_dexpi_xml(path)
        except Exception as exc:  # noqa: BLE001
            exceptions.append(f"{path.name}:{type(exc).__name__}:{exc}")
            continue
        got = entity_counts(graph)
        exp = pins[path.name]
        assert file_sha256(path) == exp["sha256"]
        assert path.stat().st_size == exp["bytes"]
        for key in ("pipelines", "equipment", "nozzles", "instruments"):
            if got[key] != exp[key]:
                mismatches.append(f"{path.name}:{key}={got[key]} want={exp[key]}")
    assert exceptions == []
    assert mismatches == []


def test_b05_manifest_sha_matches_files():
    import json

    manifest = json.loads((DEXPI13 / "fetch_manifest.json").read_text(encoding="utf-8"))
    by_name = {row["name"]: row for row in manifest if row.get("sha256") and str(row.get("name", "")).endswith(".xml")}
    pins = load_pins()["counts"]
    for name, exp in pins.items():
        row = by_name[name]
        assert row["sha256"] == exp["sha256"]
        assert row["bytes"] == exp["bytes"]
        assert row.get("license") == "CC-BY-4.0"
