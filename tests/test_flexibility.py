"""B13: ASME B31.3 319.4.1 flexibility screen + U-loop on a 200 °C line."""

from __future__ import annotations

from threadforge.flexibility import (
    B31_3_319_4_1_K_SI,
    STATUS_NEEDS,
    STATUS_NO_TEMP,
    STATUS_PASS,
    crafted_hot_line_graph,
    flexibility_ratio,
    screen_graph,
    screen_line,
    thermal_y_mm,
)
from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import generate_routes_astar
from threadforge.tables import B31_3_C1_CS_MM_PER_M, table_c1_epsilon_mm_per_m


def test_table_c1_and_319_4_1_cited():
    assert B31_3_C1_CS_MM_PER_M[204.0] == 2.16
    eps200 = table_c1_epsilon_mm_per_m(200.0)
    # Linear interpolate 149 → 204
    expect = 1.50 + (200.0 - 149.0) / (204.0 - 149.0) * (2.16 - 1.50)
    assert abs(eps200 - expect) < 1e-9
    assert B31_3_319_4_1_K_SI == 208000.0
    doc = table_c1_epsilon_mm_per_m.__doc__ or ""
    assert "Table C-1" in doc
    scr = screen_line([(0, 0, 0), (10, 0, 0)], '6"', None)
    assert "319.4.1" in scr["citation"] and "C-1" in scr["citation"]


def test_rich_lines_no_design_temp():
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    screens = screen_graph(g)
    assert set(screens) == set(g.pipelines)
    assert all(s["status"] == STATUS_NO_TEMP for s in screens.values())
    for r in g.routes.values():
        assert r["flex_screen"]["status"] == STATUS_NO_TEMP


def test_crafted_200c_needs_analysis_and_uloop():
    g = crafted_hot_line_graph(200.0, 10.0)
    scr = screen_graph(g)["LINE-HOT-200C"]
    assert scr["status"] == STATUS_NEEDS
    assert scr["design_temp_c"] == 200.0
    assert scr["u_loop"] is not None
    assert scr["u_loop"]["kind"] == "u_loop"
    assert scr["u_loop"]["protrusion_m"] > 0
    assert "319.4.1" in scr["u_loop"]["formula"]
    # Formula check: D·Y/(L−U)² is inf on a straight run (L=U).
    assert scr["ratio"] == "inf" or float(scr["ratio"]) > 208000
    # Proposed loop must bring the ratio to ≤ K.
    new_r = scr["u_loop"]["proposed_ratio"]
    assert new_r is not None and new_r <= 208000.0
    # Hand-check Y = ε(200) * 10 m
    y = thermal_y_mm(200.0, 10.0)
    assert abs(scr["Y_mm"] - y) < 1e-6
    # A long wiggly line at 20 °C-ish with lots of L−U should pass.
    wiggly = [(0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 20.0, 0.0), (0.0, 20.0, 0.0)]
    ok = screen_line(wiggly, '2"', 38.0)
    assert ok["status"] == STATUS_PASS
    assert flexibility_ratio(ok["D_mm"], ok["Y_mm"], ok["L_m"], ok["U_m"]) <= 208000
