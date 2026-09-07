"""D7: public engineering tables with hand-computed checks."""

from __future__ import annotations

from threadforge.generators import build_test_packs, generate_quantities
from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import route_pipeline, support_placeholders_engineered
from threadforge.tables import (
    flange_bolts,
    hydrotest_pressure_barg,
    long_radius_elbow_m,
    mass_per_m,
    od_mm,
    support_span_m,
    wall_thickness_mm,
)


def test_six_inch_sch40_weight_within_1pct():
    # Hand check: OD=168.3 mm, t=7.11 mm → ID=154.08 mm
    # area = π/4*(0.1683²-0.15408²)=0.003599 m²; ×7850 ≈ 28.25 kg/m
    kg = mass_per_m('6"', "40")
    assert abs(kg - 28.26) / 28.26 <= 0.01


def test_od_and_wall_b36():
    assert abs(od_mm('6"') - 168.3) < 0.05
    assert abs(wall_thickness_mm('6"', "40") - 7.11) < 0.05


def test_support_span_mss():
    assert support_span_m('6"') == 5.2
    assert support_span_m('2"') == 3.4


def test_lr_elbow_b16_9():
    # 6" → 1.5*6*0.0254 = 0.2286 m
    assert abs(long_radius_elbow_m('6"') - 0.2286) < 1e-6


def test_flange_bolts_b16_5():
    assert flange_bolts('6"', 150) == (8, 0.75)


def test_test_pressure_b31_3():
    assert hydrotest_pressure_barg(10.0) == 15.0
    assert hydrotest_pressure_barg(None) is None


def test_quantities_include_weight():
    g = load_fixture("sample_pid_rich.xml")
    art = generate_quantities(g)
    for row in art.payload["rows"]:
        assert "weight_kg" in row
        assert row["mass_kg_per_m"] > 0
        assert "bolts" in row
        assert "gaskets" in row
        assert "surface_m2" in row


def test_supports_use_span_and_bends():
    g = load_fixture("sample_pid.xml")
    pipe = g.pipelines["LINE-120-P-1001"]
    r = route_pipeline(g, pipe)
    pts = [(p["x"], p["y"], p["z"]) for p in r["points"]]
    supports = support_placeholders_engineered(pts, pipe.nominal_bore)
    types = {s["type"] for s in supports}
    assert "near_bend" in types or "near_nozzle" in types
    assert any(s.get("type") == "placeholder" for s in supports) or len(supports) >= 2


def test_test_pack_missing_design_pressure():
    g = load_fixture("sample_pid.xml")
    packs = build_test_packs(g)
    assert packs
    assert any(p.metadata.get("test_pressure_status") == "missing_design_pressure" for p in packs)


def test_flange_thickness_b16_5_table8():
    from threadforge.tables import FLANGE_THICKNESS_MM_CL150, flange_thickness_m

    assert FLANGE_THICKNESS_MM_CL150[4.0] == 23.9
    assert FLANGE_THICKNESS_MM_CL150[5.0] == 23.9
    assert FLANGE_THICKNESS_MM_CL150[6.0] == 25.4
    assert FLANGE_THICKNESS_MM_CL150[8.0] == 28.4
    assert abs(flange_thickness_m('6"') - 0.0254) < 1e-9
    assert "Table 8" in (flange_thickness_m.__doc__ or "")
