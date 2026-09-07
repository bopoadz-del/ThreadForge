"""E4: non-zero PCF fittings from B16 tables."""

from __future__ import annotations

from threadforge.generators import write_pcf_text
from threadforge.ingest_dexpi import load_fixture
from threadforge.pcf_reader import (
    assert_contiguous,
    assert_gasket_flanked_by_flanges,
    assert_no_zero_length,
    parse_pcf,
    total_centreline_length_mm,
)
from threadforge.routing import ensure_routes, get_route
from threadforge.tables import (
    flange_thickness_m,
    gasket_thickness_m,
    reducer_face_to_face_m,
    valve_face_to_face_m,
)


def test_b16_tables_cited_positive():
    assert flange_thickness_m('6"') > 0.02
    assert gasket_thickness_m() == 0.003
    assert reducer_face_to_face_m('6"', '4"') > 0.1
    assert valve_face_to_face_m('4"') > 0.2
    # docstrings cite standards
    assert "B16.5" in (flange_thickness_m.__doc__ or "")
    assert "B16.9" in (reducer_face_to_face_m.__doc__ or "")
    assert "B16.10" in (valve_face_to_face_m.__doc__ or "")


def test_pcf_fittings_non_zero_reducer_flange_gasket_valve():
    g = load_fixture()
    ensure_routes(g)
    # Line with flange/gasket/reducer
    lid = "LINE-120-P-1001"
    route = get_route(g, lid)
    route_len_m = float(route["length_m"])
    text = write_pcf_text(g, lid)
    doc = parse_pcf(text)
    assert_contiguous(doc, tol_mm=2.0)
    assert_no_zero_length(doc)
    assert_gasket_flanked_by_flanges(doc)

    flanges = [c for c in doc.components if c.kind == "FLANGE"]
    gaskets = [c for c in doc.components if c.kind == "GASKET"]
    reducers = [c for c in doc.components if c.kind == "REDUCER"]
    assert gaskets, "expected gasket"
    assert len(flanges) >= 2 and len(flanges) % 2 == 0
    assert reducers, "expected reducer"
    for red in reducers:
        assert len(red.end_points) >= 2
        b0, b1 = red.end_points[0].bore, red.end_points[1].bore
        assert b0 is not None and b1 is not None
        assert abs(b0 - b1) > 1.0, "reducer bores must differ"

    total_m = total_centreline_length_mm(doc) / 1000.0
    # Fitting spans consume pipe centreline — total should stay within ±0.5% of route
    assert abs(total_m - route_len_m) / max(route_len_m, 1e-6) <= 0.005, (
        f"total {total_m} vs route {route_len_m}"
    )

    # Valve line
    lid_v = "LINE-120-P-1002"
    text_v = write_pcf_text(g, lid_v)
    doc_v = parse_pcf(text_v)
    assert_no_zero_length(doc_v)
    valves = [c for c in doc_v.components if c.kind == "VALVE"]
    assert valves and valves[0].length_mm() > 50.0


def test_pcf_six_inch_flange_uses_25_4():
    from threadforge.tables import flange_thickness_m
    assert abs(flange_thickness_m('6"') * 1000 - 25.4) < 1e-9
