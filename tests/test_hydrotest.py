"""B22: B31.3 345.4.2 hydrotest + B16.5 P-T + C01 vents/drains."""

from threadforge.hydrotest import C01_HYDRO_PIN, build_hydrotest_packs, high_low_points
from threadforge.ingest_dexpi import load_fixture
from threadforge.tables import (
    B16_5_PT_CITE,
    B31_3_345_4_2_CITE,
    b16_5_pt_rating_bar,
    b31_3_345_4_2_test_pressure,
    infer_flange_class,
)


def test_345_4_2_capped_by_b16_5():
    calc = b31_3_345_4_2_test_pressure(60.0, 100.0, 21.0)
    assert infer_flange_class(60.0, 100.0) == 400
    assert abs(float(calc["P_T_uncapped_barg"]) - 90.0) < 1e-9
    assert abs(b16_5_pt_rating_bar(400, 21.0) - 68.1) < 1e-9
    assert abs(float(calc["test_pressure_barg"]) - 68.1) < 1e-9
    assert calc["capped"] is True
    assert "345.4.2" in B31_3_345_4_2_CITE
    assert "2-1.1" in B16_5_PT_CITE


def test_st_over_s_hot_line():
    calc = b31_3_345_4_2_test_pressure(10.0, 316.0, 21.0)
    assert float(calc["St_over_S"]) > 1.0
    assert float(calc["P_T_uncapped_barg"]) > 15.0


def test_high_low_from_geometry():
    ext = high_low_points([(0.0, 0.0, 5.0), (6.0, 0.0, 9.0), (12.0, 0.0, 3.0)])
    assert {v["z"] for v in ext["vents"]} == {9.0}
    assert {d["z"] for d in ext["drains"]} == {3.0}


def test_c01_hydrotest_pin():
    g = load_fixture("C01V04-VER.EX01.xml")
    packs = build_hydrotest_packs(g)
    by = {p.system_id: p for p in packs}
    assert len(packs) == C01_HYDRO_PIN["pack_count"]
    mnb = by["SYS-MNb"].metadata
    assert abs(float(mnb["test_pressure_barg"]) - 68.1) < 1e-6
    assert mnb["flange_class"] == 400
    assert mnb["test_medium"] == "water"
    assert 9.0 in {float(v["z"]) for v in mnb["vents"]}
    assert 3.0 in {float(d["z"]) for d in mnb["drains"]}
    stops = set(by["SYS-MNc"].metadata.get("boundary_stops") or [])
    assert {"BlindFlange-1", "BlindFlange-2"} <= stops
