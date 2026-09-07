"""D11: golden baseline proves old PCF defect; new emitter is contiguous."""

from __future__ import annotations

from pathlib import Path

from threadforge.generators import write_pcf_text
from threadforge.ingest_dexpi import load_fixture
from threadforge.pcf_reader import PCFParseError, assert_contiguous, overlaps_pipe_elbow, parse_pcf

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "golden" / "baseline" / "pcf" / "120-P-1001.pcf"


def test_golden_baseline_pcf_fails_reader_contiguity():
    doc = parse_pcf(BASELINE)
    assert overlaps_pipe_elbow(doc)
    try:
        assert_contiguous(doc)
        raised = False
    except PCFParseError:
        raised = True
    assert raised


def test_current_emitter_passes_contiguity():
    g = load_fixture()
    doc = parse_pcf(write_pcf_text(g, "LINE-120-P-1001"))
    assert_contiguous(doc)
    assert overlaps_pipe_elbow(doc) == []
