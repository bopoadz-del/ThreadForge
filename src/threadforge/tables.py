"""Public engineering tables (cited). No invented vendor catalogues.

Sources (public / standards summaries commonly republished):
- ASME B36.10M / B36.19M — NPS → OD and schedule wall thickness for steel pipe.
- Steel density 7850 kg/m³ — common engineering value for carbon steel.
- MSS SP-58 — pipe support spacing (water-filled steel pipe) guidance.
- ASME B16.9 — long-radius elbow centreline radius = 1.5 × NPS.
- ASME B16.5 — flange bolt count/size and minimum flange thickness for Class 150 / 300.
- ASME B16.9 — butt-welding fittings: long-radius elbows; concentric reducer end-to-end.
- ASME B16.10 — valve face-to-face / end-to-end dimensions (Class 150 gate / globe).
- Gasket thickness 3 mm — common compressed non-asbestos sheet practice (not a code table).
- ASME B31.3 paragraph 345.4.2 — hydrostatic test pressure P_T = 1.5 × P × S_T / S.
- ASME B16.5 Table 2-1.1 (Group 1.1) — flange pressure-temperature ratings (bar).
- ASME B31.3 Appendix A Table A-1 — A106 Gr.B basic allowable stress (MPa).
- ASME B31.3 Appendix C Table C-1 — carbon-steel thermal expansion (mm/m from 21 °C).
- ASME B31.3 paragraph 319.4.1 — empirical flexibility criterion (SI K = 208000).
"""

from __future__ import annotations

import math
from typing import Optional

# NPS (inch) → OD (mm). ASME B36.10M Table 1 (selected common sizes).
NPS_OD_MM: dict[float, float] = {
    0.5: 21.3,
    0.75: 26.7,
    1.0: 33.4,
    1.5: 48.3,
    2.0: 60.3,
    3.0: 88.9,
    4.0: 114.3,
    6.0: 168.3,
    8.0: 219.1,
    10.0: 273.0,
    12.0: 323.8,
    24.0: 610.0,  # ASME B36.10M Table 1 NPS 24
}

# Schedule → wall thickness mm by NPS. ASME B36.10M (selected).
# Keys: (nps_inch, schedule_name)
WALL_THICKNESS_MM: dict[tuple[float, str], float] = {
    (2.0, "40"): 3.91,
    (3.0, "40"): 5.49,
    (4.0, "40"): 6.02,
    (6.0, "40"): 7.11,
    (8.0, "40"): 8.18,
    (6.0, "80"): 10.97,
    (4.0, "80"): 8.56,
    (2.0, "80"): 5.54,
    (3.0, "80"): 7.62,
    (24.0, "40"): 17.48,  # ASME B36.10M NPS 24 Sch 40 / STD
}

STEEL_DENSITY_KG_M3 = 7850.0  # carbon steel

# MSS SP-58 suggested support spacing (m) for water-filled CS pipe (approx table).
# Values are commonly republished spans for Sch40 water service.
SUPPORT_SPAN_M: dict[float, float] = {
    0.5: 2.1,
    0.75: 2.4,
    1.0: 2.7,
    1.5: 3.0,
    2.0: 3.4,
    3.0: 4.0,
    4.0: 4.3,
    6.0: 5.2,
    8.0: 5.8,
    10.0: 6.4,
    12.0: 7.0,
}

# ASME B16.5 Class 150 / 300 bolt counts and sizes (UNC).
# (nps, class) → (bolt_count, bolt_dia_inch)
FLANGE_BOLTS: dict[tuple[float, int], tuple[int, float]] = {
    (2.0, 150): (4, 0.625),
    (3.0, 150): (4, 0.625),
    (4.0, 150): (8, 0.625),
    (6.0, 150): (8, 0.75),
    (8.0, 150): (8, 0.75),
    (2.0, 300): (8, 0.625),
    (3.0, 300): (8, 0.75),
    (4.0, 300): (8, 0.75),
    (6.0, 300): (12, 0.75),
    (8.0, 300): (12, 0.875),
}


def parse_nps_inch(nominal_bore: Optional[str]) -> float:
    if not nominal_bore:
        return 4.0
    s = nominal_bore.replace('"', "").replace("''", "").strip().upper()
    s = s.replace("DN", "").replace("NB", "").strip()
    inch_map = {"1/2": 0.5, "3/4": 0.75, "1-1/2": 1.5, "1.5": 1.5}
    if s in inch_map:
        return inch_map[s]
    try:
        v = float(s)
        if v > 30:  # treat as mm DN approx
            return v / 25.4
        return v
    except ValueError:
        return 4.0


def od_mm(nominal_bore: Optional[str]) -> float:
    """Outside diameter mm — ASME B36.10M."""
    nps = parse_nps_inch(nominal_bore)
    if nps in NPS_OD_MM:
        return NPS_OD_MM[nps]
    # nearest
    keys = sorted(NPS_OD_MM)
    nearest = min(keys, key=lambda k: abs(k - nps))
    return NPS_OD_MM[nearest]


def wall_thickness_mm(nominal_bore: Optional[str], schedule: str = "40") -> float:
    """Wall thickness mm — ASME B36.10M schedule table (selected)."""
    nps = parse_nps_inch(nominal_bore)
    sch = str(schedule).replace("Sch", "").replace("SCH", "").replace("S", "").strip() or "40"
    if (nps, sch) in WALL_THICKNESS_MM:
        return WALL_THICKNESS_MM[(nps, sch)]
    # fallback interpolate by OD*0.04
    return od_mm(nominal_bore) * 0.04


def mass_per_m(nominal_bore: Optional[str], schedule: str = "40") -> float:
    """Pipe mass kg/m = ρ × π/4 × (OD² − ID²).

    OD/wall from B36.10; density 7850 kg/m³ (CS).
    """
    od = od_mm(nominal_bore) / 1000.0
    t = wall_thickness_mm(nominal_bore, schedule) / 1000.0
    id_ = od - 2 * t
    area = math.pi / 4.0 * (od * od - id_ * id_)
    return area * STEEL_DENSITY_KG_M3


def support_span_m(nominal_bore: Optional[str]) -> float:
    """Suggested support spacing (m) — MSS SP-58 water-filled CS guidance."""
    nps = parse_nps_inch(nominal_bore)
    if nps in SUPPORT_SPAN_M:
        return SUPPORT_SPAN_M[nps]
    keys = sorted(SUPPORT_SPAN_M)
    nearest = min(keys, key=lambda k: abs(k - nps))
    return SUPPORT_SPAN_M[nearest]


def long_radius_elbow_m(nominal_bore: Optional[str]) -> float:
    """Long-radius elbow centreline radius (m) — ASME B16.9: R = 1.5 × NPS."""
    nps = parse_nps_inch(nominal_bore)
    return 1.5 * nps * 0.0254


def flange_bolts(nominal_bore: Optional[str], flange_class: int = 150) -> tuple[int, float]:
    """(count, bolt_dia_inch) — ASME B16.5 Class 150/300."""
    nps = parse_nps_inch(nominal_bore)
    key = (nps, int(flange_class))
    if key in FLANGE_BOLTS:
        return FLANGE_BOLTS[key]
    # nearest nps
    candidates = [k for k in FLANGE_BOLTS if k[1] == int(flange_class)]
    if not candidates:
        return (8, 0.75)
    nearest = min(candidates, key=lambda k: abs(k[0] - nps))
    return FLANGE_BOLTS[nearest]


def hydrotest_pressure_barg(design_pressure_barg: Optional[float]) -> Optional[float]:
    """Hydrotest = 1.5 × design — ASME B31.3 345.4.2 with S_T/S = 1 (same T).

    Full 345.4.2 (S_T/S and B16.5 P-T cap) is ``b31_3_345_4_2_test_pressure``.
    """
    if design_pressure_barg is None:
        return None
    return 1.5 * float(design_pressure_barg)


# ASME B31.3 paragraph 345.4.2 — Hydrostatic Test Pressure (metallic piping):
#   P_T = 1.5 × P × S_T / S
#   P_T shall not exceed the test pressure of any component (flange rating).
# Citation: ASME B31.3 Process Piping, paragraph 345.4.2.
B31_3_345_4_2_FACTOR = 1.5
B31_3_345_4_2_CITE = (
    "ASME B31.3 Process Piping, paragraph 345.4.2: hydrostatic test pressure "
    "P_T = 1.5 × P × S_T / S, not exceeding any component (flange) rating"
)

# ASME B31.3 Appendix A Table A-1 — A106 Grade B seamless, basic allowable S (MPa).
# Selected temperatures. Citation: ASME B31.3 Process Piping, Appendix A, Table A-1
# (A106 Gr.B / A53 Gr.B Group). 20.0 ksi = 137.9 MPa through 204 °C (400 °F).
B31_3_A1_A106B_S_MPA: dict[float, float] = {
    21.0: 137.9,
    38.0: 137.9,
    100.0: 137.9,
    149.0: 137.9,
    204.0: 137.9,
    260.0: 130.3,  # 18.9 ksi at 500 °F
    316.0: 119.3,  # 17.3 ksi at 600 °F
    343.0: 115.8,
}

# ASME B16.5-2020 Table 2-1.1 (metric) — Group 1.1 (A105 / A106-B / A53-B)
# working pressure (bar, gauge) vs temperature (°C) and class.
# Citation: ASME B16.5 Pipe Flanges and Flanged Fittings, Table 2-1.1 (Group 1.1).
B16_5_PT_GROUP_1_1_BAR: dict[int, dict[float, float]] = {
    150: {38.0: 19.6, 50.0: 19.2, 100.0: 17.7, 150.0: 15.8, 200.0: 13.8, 250.0: 12.1, 300.0: 10.2, 350.0: 7.6},
    300: {38.0: 51.1, 50.0: 50.1, 100.0: 46.6, 150.0: 45.1, 200.0: 43.8, 250.0: 41.9, 300.0: 39.8, 350.0: 37.6},
    400: {38.0: 68.1, 50.0: 66.8, 100.0: 62.1, 150.0: 60.1, 200.0: 58.4, 250.0: 55.9, 300.0: 53.1, 350.0: 50.1},
    600: {38.0: 102.1, 50.0: 100.2, 100.0: 93.2, 150.0: 90.2, 200.0: 87.6, 250.0: 83.9, 300.0: 79.6, 350.0: 75.1},
    900: {38.0: 153.2, 50.0: 150.4, 100.0: 139.8, 150.0: 135.2, 200.0: 131.4, 250.0: 125.8, 300.0: 119.5, 350.0: 112.7},
    1500: {38.0: 255.3, 50.0: 250.6, 100.0: 233.0, 150.0: 225.4, 200.0: 219.0, 250.0: 209.7, 300.0: 199.1, 350.0: 187.8},
    2500: {38.0: 425.4, 50.0: 417.7, 100.0: 388.3, 150.0: 375.4, 200.0: 365.0, 250.0: 349.5, 300.0: 331.8, 350.0: 313.0},
}
B16_5_PT_CITE = (
    "ASME B16.5 Pipe Flanges and Flanged Fittings, Table 2-1.1 "
    "(Group 1.1 pressure-temperature ratings, bar)"
)
B16_5_PT_CLASSES: tuple[int, ...] = (150, 300, 400, 600, 900, 1500, 2500)

# Service → hydrostatic test medium. B31.3 345.4 is a hydrostatic (liquid) test;
# water is the default medium. Mapped C01 TrainingTestCases FluidCodes included.
# Citation: ASME B31.3 paragraph 345.4 (hydrostatic); service table is plant practice.
SERVICE_TEST_MEDIUM: dict[str, str] = {
    "PROCESS": "water",
    "HYDROCARBON": "water",
    "LPG": "water",
    "GAS": "water",
    "STEAM": "water",
    "UTILITY": "water",
    "DRAIN": "water",
    "VENT": "water",
    "NITROGEN": "water",
    "MNB": "water",
    "MNC": "water",
    "WKA": "water",
    "WKB": "water",
    "QSA": "water",
    "QSB": "water",
}
SERVICE_TEST_MEDIUM_CITE = (
    "ASME B31.3 paragraph 345.4 hydrostatic test (liquid); "
    "service→medium table defaults to water"
)


def _interp_table(table: dict[float, float], temp_c: float) -> float:
    t = float(temp_c)
    if t in table:
        return table[t]
    keys = sorted(table)
    if t <= keys[0]:
        return table[keys[0]]
    if t >= keys[-1]:
        return table[keys[-1]]
    lo = max(k for k in keys if k <= t)
    hi = min(k for k in keys if k >= t)
    if hi == lo:
        return table[lo]
    frac = (t - lo) / (hi - lo)
    return table[lo] + frac * (table[hi] - table[lo])


def allowable_stress_mpa(temp_c: float, material: str = "A106B") -> float:
    """Basic allowable stress S (MPa) — B31.3 Appendix A Table A-1 (A106 Gr.B).

    Citation: ASME B31.3 Process Piping, Appendix A, **Table A-1** (A106 Grade B).
    ``material`` other than A106-family still uses this public A106-B row (no
    vendor catalogue).
    """
    _ = material
    return _interp_table(B31_3_A1_A106B_S_MPA, temp_c)


def b16_5_pt_rating_bar(flange_class: int, temp_c: float) -> float:
    """Flange working pressure (bar) — B16.5 Table 2-1.1 Group 1.1.

    Citation: ASME B16.5, **Table 2-1.1** (Group 1.1).
    """
    cls = int(flange_class)
    if cls not in B16_5_PT_GROUP_1_1_BAR:
        nearest = min(B16_5_PT_CLASSES, key=lambda c: abs(c - cls))
        cls = nearest
    return _interp_table(B16_5_PT_GROUP_1_1_BAR[cls], temp_c)


def infer_flange_class(design_pressure_barg: float, design_temp_c: float) -> int:
    """Lowest B16.5 class whose Table 2-1.1 rating at T ≥ design P."""
    p = float(design_pressure_barg)
    t = float(design_temp_c)
    for cls in B16_5_PT_CLASSES:
        if b16_5_pt_rating_bar(cls, t) + 1e-9 >= p:
            return cls
    return B16_5_PT_CLASSES[-1]


def b31_3_345_4_2_test_pressure(
    design_pressure_barg: float,
    design_temp_c: float,
    test_temp_c: float = 21.0,
    flange_class: Optional[int] = None,
    material: str = "A106B",
) -> dict[str, float | int | str | bool]:
    """Hydrostatic test pressure per B31.3 345.4.2, capped by B16.5 P-T.

    P_T_uncapped = 1.5 × P × S_T / S
    P_T = min(P_T_uncapped, B16.5 Table 2-1.1 rating of the class at test T)
    """
    p = float(design_pressure_barg)
    s = allowable_stress_mpa(design_temp_c, material)
    s_t = allowable_stress_mpa(test_temp_c, material)
    ratio = s_t / s if s > 0 else 1.0
    uncapped = B31_3_345_4_2_FACTOR * p * ratio
    cls = int(flange_class) if flange_class is not None else infer_flange_class(p, design_temp_c)
    cap = b16_5_pt_rating_bar(cls, test_temp_c)
    pt = min(uncapped, cap)
    return {
        "design_pressure_barg": p,
        "design_temp_c": float(design_temp_c),
        "test_temp_c": float(test_temp_c),
        "S_mpa": round(s, 3),
        "S_T_mpa": round(s_t, 3),
        "St_over_S": round(ratio, 6),
        "P_T_uncapped_barg": round(uncapped, 4),
        "flange_class": cls,
        "flange_rating_barg": round(cap, 4),
        "test_pressure_barg": round(pt, 4),
        "capped": uncapped > cap + 1e-9,
        "citation": B31_3_345_4_2_CITE,
        "pt_table": B16_5_PT_CITE,
        "stress_table": "ASME B31.3 Appendix A Table A-1 (A106 Gr.B)",
    }


def test_medium_for_service(service: Optional[str]) -> str:
    """Hydrotest medium from the service table (B31.3 345.4 → water)."""
    key = (service or "PROCESS").strip().upper()
    if key in SERVICE_TEST_MEDIUM:
        return SERVICE_TEST_MEDIUM[key]
    return "water"


# ASME B16.5 Class 150 minimum flange thickness tf (mm) — raised-face welding-neck.
# Citation: ASME B16.5 Pipe Flanges and Flanged Fittings, Table 8 (Class 150), selected NPS.
FLANGE_THICKNESS_MM_CL150: dict[float, float] = {
    0.5: 11.2,
    0.75: 12.7,
    1.0: 14.3,
    1.5: 17.5,
    2.0: 19.1,
    3.0: 22.3,
    4.0: 23.9,   # Table 8 NPS 4
    5.0: 23.9,   # Table 8 NPS 5
    6.0: 25.4,   # Table 8 NPS 6
    8.0: 28.4,   # Table 8 NPS 8
    10.0: 28.6,
    12.0: 30.2,
}

# ASME B16.9 concentric reducer overall length (mm) keyed by (NPS_large, NPS_small).
# Selected rows from ASME B16.9 Table I-1 / I-2 (butt-welding fittings).
REDUCER_LENGTH_MM: dict[tuple[float, float], float] = {
    (3.0, 2.0): 89.0,
    (4.0, 3.0): 102.0,
    (4.0, 2.0): 102.0,
    (6.0, 4.0): 140.0,
    (6.0, 3.0): 140.0,
    (8.0, 6.0): 152.0,
    (8.0, 4.0): 152.0,
    (10.0, 8.0): 178.0,
    (12.0, 10.0): 203.0,
    (12.0, 8.0): 203.0,
}

# ASME B16.10 Class 150 gate valve face-to-face (mm) — flanged ends.
# Selected from ASME B16.10 Table 1 (Class 150).
VALVE_F2F_MM_CL150_GATE: dict[float, float] = {
    0.5: 108.0,
    0.75: 117.0,
    1.0: 127.0,
    1.5: 165.0,
    2.0: 178.0,
    3.0: 203.0,
    4.0: 229.0,
    6.0: 267.0,
    8.0: 292.0,
    10.0: 330.0,
    12.0: 356.0,
}

GASKET_THICKNESS_MM = 3.0  # common compressed sheet practice

# ASME B31.3 Appendix C Table C-1 — carbon steel (A53 / A106 group).
# Total linear thermal expansion, mm/m, from 21 °C (70 °F). Selected rows.
# Citation: ASME B31.3 Process Piping, Appendix C, Table C-1.
B31_3_C1_CS_MM_PER_M: dict[float, float] = {
    21.0: 0.00,
    38.0: 0.18,
    93.0: 0.86,
    149.0: 1.50,
    204.0: 2.16,
    260.0: 2.88,
    316.0: 3.62,
    371.0: 4.41,
}

# ASME B31.3 §319.4.1 SI constant (D, Y in mm; L, U in m) for ferrous materials.
B31_3_319_4_1_K_SI = 208000.0

# ASME B31.3 paragraph 341.4.1 — Examination, Normal Fluid Service.
# (a) visual examination of all fabrication.
# (b)(1) not less than 5% of circumferential butt and miter groove welds
#     shall be examined by random radiography or ultrasonic examination.
# Citation: ASME B31.3 Process Piping, paragraph 341.4.1 (Normal Fluid Service).
B31_3_341_4_1_NORMAL_RT_PCT = 5.0
B31_3_341_4_1_CITE = (
    "ASME B31.3 Process Piping, paragraph 341.4.1 Normal Fluid Service "
    "(b)(1): not less than 5% of circumferential butt and miter groove welds "
    "shall be examined by random radiography or ultrasonic examination"
)


def table_c1_epsilon_mm_per_m(design_temp_c: float) -> float:
    """Carbon-steel thermal expansion mm/m from 21 °C — B31.3 Table C-1 (interpolated).

    Citation: ASME B31.3 Process Piping, Appendix C, **Table C-1** (carbon steel).
    """
    t = float(design_temp_c)
    table = B31_3_C1_CS_MM_PER_M
    if t in table:
        return table[t]
    keys = sorted(table)
    if t <= keys[0]:
        return table[keys[0]]
    if t >= keys[-1]:
        return table[keys[-1]]
    lo = max(k for k in keys if k <= t)
    hi = min(k for k in keys if k >= t)
    if hi == lo:
        return table[lo]
    frac = (t - lo) / (hi - lo)
    return table[lo] + frac * (table[hi] - table[lo])


def insulation_od_mm(nominal_bore: Optional[str], insulation_mm: float = 0.0) -> float:
    """Outside diameter over insulation (mm) = B36.10 OD + 2 × insulation."""
    return od_mm(nominal_bore) + 2.0 * float(insulation_mm)


def flange_thickness_m(nominal_bore: Optional[str], flange_class: int = 150) -> float:
    """Flange thickness (m) — ASME B16.5 Class 150 minimum tf (selected NPS).

    Citation: ASME B16.5 Pipe Flanges and Flanged Fittings, **Table 8** (Class 150
    minimum flange thickness tf). Class 300 not tabulated here → Class 150 used.
    """
    nps = parse_nps_inch(nominal_bore)
    table = FLANGE_THICKNESS_MM_CL150
    if nps in table:
        return table[nps] / 1000.0
    nearest = min(table, key=lambda k: abs(k - nps))
    return table[nearest] / 1000.0


def gasket_thickness_m() -> float:
    """Gasket thickness (m) — 3 mm compressed non-asbestos sheet practice.

    Not an ASME dimensional table; documented plant/practice default for PCF span.
    """
    return GASKET_THICKNESS_MM / 1000.0


def reducer_face_to_face_m(
    bore_large: Optional[str],
    bore_small: Optional[str] = None,
) -> float:
    """Concentric reducer end-to-end length (m) — ASME B16.9.

    Citation: ASME B16.9 Factory-Made Wrought Buttwelding Fittings, Table I-1/I-2
    overall length for concentric reducers (selected size pairs).
    """
    n_large = parse_nps_inch(bore_large)
    if bore_small is None:
        # one standard size step down
        sizes = sorted(NPS_OD_MM)
        smaller = [s for s in sizes if s < n_large - 1e-9]
        n_small = smaller[-1] if smaller else max(0.5, n_large - 1.0)
    else:
        n_small = parse_nps_inch(bore_small)
    if n_small > n_large:
        n_large, n_small = n_small, n_large
    key = (n_large, n_small)
    if key in REDUCER_LENGTH_MM:
        return REDUCER_LENGTH_MM[key] / 1000.0
    # nearest large
    candidates = [k for k in REDUCER_LENGTH_MM if abs(k[0] - n_large) < 0.6]
    if candidates:
        best = min(candidates, key=lambda k: abs(k[1] - n_small))
        return REDUCER_LENGTH_MM[best] / 1000.0
    return max(0.089, 0.025 * n_large)  # conservative fallback from B16.9 trend


def valve_face_to_face_m(nominal_bore: Optional[str], flange_class: int = 150) -> float:
    """Valve face-to-face (m) — ASME B16.10 Class 150 gate (flanged).

    Citation: ASME B16.10 Face-to-Face and End-to-End Dimensions of Valves,
    Table 1 Class 150 gate valves (selected NPS).
    """
    nps = parse_nps_inch(nominal_bore)
    table = VALVE_F2F_MM_CL150_GATE
    if nps in table:
        return table[nps] / 1000.0
    nearest = min(table, key=lambda k: abs(k - nps))
    return table[nearest] / 1000.0


def next_smaller_bore(nominal_bore: Optional[str]) -> str:
    """Return a one-step-smaller DN/NPS string for reducer bore_out."""
    nps = parse_nps_inch(nominal_bore)
    sizes = sorted(NPS_OD_MM)
    smaller = [s for s in sizes if s < nps - 1e-9]
    if not smaller:
        return "DN40" if nps >= 2 else "DN15"
    s = smaller[-1]
    # Prefer DN labelling when input looked metric
    if nominal_bore and "DN" in nominal_bore.upper():
        return f"DN{int(round(s * 25.4))}"
    # inch string
    if s == int(s):
        return f'{int(s)}"'
    return f'{s}"'
