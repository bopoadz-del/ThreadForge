"""D1: PCF structural validity + round-trip invariants.

These tests FAIL on baseline golden PCF (elbow overlaps pipes) and PASS on
the sequential emitter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from threadforge.generators import write_pcf_text
from threadforge.pcf_reader import (
    PCFParseError,
    assert_contiguous,
    bore_continuity,
    overlaps_pipe_elbow,
    parse_pcf,
    total_centreline_length_mm,
)
from threadforge.routing import route_pipeline

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PCF = ROOT / "tests" / "golden" / "baseline" / "pcf" / "120-P-1001.pcf"


def test_baseline_golden_pcf_has_elbow_overlap():
    """Prove the old defect: baseline PCF elbows overlap pipes."""
    doc = parse_pcf(BASELINE_PCF)
    msgs = overlaps_pipe_elbow(doc)
    assert msgs, "expected baseline elbow/pipe overlap defect"
    # Contiguity of PIPE→ELBOW sequence is also broken in baseline
    # (elbows appended after all pipes, not interleaved).
    with pytest.raises(PCFParseError):
        assert_contiguous(doc)


def test_new_pcf_contiguous_no_overlap(graph):
    for lid, pipe in graph.pipelines.items():
        text = write_pcf_text(graph, lid)
        doc = parse_pcf(text)
        assert doc.pipeline_reference == pipe.line_number
        assert "ISOGEN-FILES" not in doc.headers
        assert_contiguous(doc, tol_mm=1.0)
        assert overlaps_pipe_elbow(doc) == []
        # Elbows use ELBW + ANGLE 9000
        elbows = [c for c in doc.components if c.kind == "ELBOW"]
        for e in elbows:
            assert e.skey == "ELBW"
            assert e.angle == 9000
            assert e.centre_point is not None


def test_pcf_length_matches_route(graph):
    lid = "LINE-120-P-1001"
    pipe = graph.pipelines[lid]
    route = route_pipeline(graph, pipe)
    doc = parse_pcf(write_pcf_text(graph, lid))
    pcf_m = total_centreline_length_mm(doc) / 1000.0
    route_m = float(route["length_m"])
    assert route_m > 0
    rel = abs(pcf_m - route_m) / route_m
    assert rel <= 0.005, f"pcf={pcf_m} route={route_m} rel={rel}"


def test_pcf_bore_continuity(graph):
    lid = "LINE-120-P-1001"
    doc = parse_pcf(write_pcf_text(graph, lid))
    # No unexpected bore jumps (reducers allowed)
    assert bore_continuity(doc) == []


def test_pcf_positioned_fittings_have_skey(graph):
    lid = "LINE-120-P-1001"
    doc = parse_pcf(write_pcf_text(graph, lid))
    kinds = {c.kind for c in doc.components}
    assert "FLANGE" in kinds or "GASKET" in kinds or "REDUCER" in kinds
    for c in doc.components:
        if c.kind in ("FLANGE", "GASKET", "VALVE", "REDUCER", "TEE"):
            assert c.skey
            assert c.tag or c.item_code


def test_pcf_materials_section(graph):
    lid = "LINE-120-P-1001"
    text = write_pcf_text(graph, lid)
    assert "\nMATERIALS\n" in text or text.strip().endswith("MATERIALS") or "MATERIALS" in text
    doc = parse_pcf(text)
    assert len(doc.materials) >= 1


def test_pcf_reader_parse_file_roundtrip(graph, tmp_path):
    lid = "LINE-120-P-1001"
    text = write_pcf_text(graph, lid)
    path = tmp_path / "line.pcf"
    path.write_text(text, encoding="utf-8")
    doc = parse_pcf(path)
    assert_contiguous(doc)
    assert doc.pipeline_reference == "120-P-1001"
