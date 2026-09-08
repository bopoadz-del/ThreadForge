"""ASME B31.3 §319.4.1 empirical flexibility screening (SI).

Criterion (ferrous materials, SI):

    D · Y / (L − U)²  ≤  208000

- D = outside diameter, mm (ASME B36.10M)
- Y = resultant thermal displacement to be absorbed, mm
      = ε(T) · U   with ε from B31.3 Appendix C **Table C-1** (carbon steel)
- L = developed length of piping between anchors, m
- U = straight-line (anchor-to-anchor) distance, m
- 208000 = SI constant from ASME B31.3 paragraph 319.4.1

Statuses: ``pass`` | ``needs_analysis`` | ``no_design_temp``.

A failing hot line gets a formula-sourced rectangular U-loop proposal
(extra developed length so (L−U) ≥ √(D·Y/208000)). Heuristic — not a
stress analysis.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Equipment, Nozzle, Pipeline
from threadforge.routing import Point3, polyline_length
from threadforge.tables import B31_3_319_4_1_K_SI, od_mm, table_c1_epsilon_mm_per_m

STATUS_PASS = "pass"
STATUS_NEEDS = "needs_analysis"
STATUS_NO_TEMP = "no_design_temp"


def developed_and_anchor(points: list[Point3]) -> tuple[float, float]:
    if len(points) < 2:
        return 0.0, 0.0
    l_m = polyline_length(points)
    a, b = points[0], points[-1]
    u_m = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)
    return l_m, u_m


def thermal_y_mm(design_temp_c: float, u_m: float) -> float:
    """Y (mm) = Table C-1 ε (mm/m) × U (m)."""
    return table_c1_epsilon_mm_per_m(design_temp_c) * u_m


def flexibility_ratio(d_mm: float, y_mm: float, l_m: float, u_m: float) -> float:
    denom = (l_m - u_m) ** 2
    if denom < 1e-12:
        return float("inf")
    return (d_mm * y_mm) / denom


def u_loop_protrusion_m(d_mm: float, y_mm: float, l_m: float, u_m: float, k: float = B31_3_319_4_1_K_SI) -> float:
    """Minimum U-loop protrusion so extra length 2P raises (L−U) to √(D·Y/K).

    Extra developed length of a rectangular U-loop of protrusion P is 2P.
    Required (L−U) = √(D·Y/K). Current slack = L−U. Need 2P ≥ required − slack.
    """
    need = math.sqrt(max(0.0, d_mm * y_mm / k))
    slack = max(0.0, l_m - u_m)
    extra = max(0.0, need - slack)
    return max(0.5, extra / 2.0)  # 0.5 m practical minimum when a loop is proposed


def screen_line(
    points: list[Point3],
    nominal_bore: Optional[str],
    design_temp_c: Optional[float],
) -> dict[str, Any]:
    """Screen one anchored polyline. Cite B31.3 319.4.1 + Table C-1."""
    cite = (
        "ASME B31.3 Process Piping, paragraph 319.4.1 "
        "(empirical flexibility criterion, SI K=208000); "
        "thermal expansion Y from Appendix C Table C-1 (carbon steel) × U"
    )
    l_m, u_m = developed_and_anchor(points)
    d_mm = od_mm(nominal_bore)
    base: dict[str, Any] = {
        "D_mm": round(d_mm, 3),
        "L_m": round(l_m, 4),
        "U_m": round(u_m, 4),
        "K_SI": B31_3_319_4_1_K_SI,
        "citation": cite,
        "standard": "ASME B31.3",
        "paragraph": "319.4.1",
        "table": "C-1",
        "u_loop": None,
    }
    if design_temp_c is None:
        base.update(
            {
                "status": STATUS_NO_TEMP,
                "Y_mm": None,
                "epsilon_mm_per_m": None,
                "design_temp_c": None,
                "ratio": None,
            }
        )
        return base
    eps = table_c1_epsilon_mm_per_m(float(design_temp_c))
    y_mm = thermal_y_mm(float(design_temp_c), u_m)
    ratio = flexibility_ratio(d_mm, y_mm, l_m, u_m)
    ok = ratio <= B31_3_319_4_1_K_SI
    base.update(
        {
            "status": STATUS_PASS if ok else STATUS_NEEDS,
            "Y_mm": round(y_mm, 4),
            "epsilon_mm_per_m": round(eps, 4),
            "design_temp_c": float(design_temp_c),
            "ratio": ratio if math.isfinite(ratio) else "inf",
        }
    )
    if not ok:
        p = u_loop_protrusion_m(d_mm, y_mm, l_m, u_m)
        new_l = l_m + 2.0 * p
        new_ratio = flexibility_ratio(d_mm, y_mm, new_l, u_m)
        base["u_loop"] = {
            "kind": "u_loop",
            "protrusion_m": round(p, 4),
            "extra_length_m": round(2.0 * p, 4),
            "formula": "2P >= sqrt(D*Y/208000) - (L-U)   [B31.3 319.4.1 SI]",
            "source": cite,
            "proposed_L_m": round(new_l, 4),
            "proposed_ratio": new_ratio if math.isfinite(new_ratio) else None,
        }
    return base


def design_temp_of(pipe: Pipeline) -> Optional[float]:
    meta = pipe.metadata or {}
    for key in ("design_temp_c", "DesignTemperature", "design_temperature_c"):
        raw = meta.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def screen_graph(graph: TopologyGraph) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for lid, pipe in graph.pipelines.items():
        route = graph.routes.get(lid) or {}
        pts = [(p["x"], p["y"], p["z"]) for p in route.get("points") or []]
        out[lid] = screen_line(pts, pipe.nominal_bore, design_temp_of(pipe))
        out[lid]["line_id"] = lid
        out[lid]["line_number"] = pipe.line_number
    return out


def crafted_hot_line_graph(temp_c: float = 200.0, length_m: float = 10.0) -> TopologyGraph:
    """Nearly-straight 6\" CS line at ``temp_c`` — fails 319.4.1 (L≈U)."""
    g = TopologyGraph()
    g.equipment["EQ-HOT-A"] = Equipment(id="EQ-HOT-A", tag="EQ-HOT-A", nozzles=["HOT-N1"])
    g.equipment["EQ-HOT-B"] = Equipment(id="EQ-HOT-B", tag="EQ-HOT-B", nozzles=["HOT-N2"])
    g.nozzles["HOT-N1"] = Nozzle(id="HOT-N1", tag="N1", equipment_id="EQ-HOT-A", x=0.0, y=0.0, z=5.0)
    g.nozzles["HOT-N2"] = Nozzle(id="HOT-N2", tag="N2", equipment_id="EQ-HOT-B", x=length_m, y=0.0, z=5.0)
    g.pipelines["LINE-HOT-200C"] = Pipeline(
        id="LINE-HOT-200C",
        line_number="HOT-200C",
        from_tag="HOT-N1",
        to_tag="HOT-N2",
        nominal_bore='6"',
        service="PROCESS",
        material="CS",
        metadata={"design_temp_c": temp_c},
    )
    g.routes["LINE-HOT-200C"] = {
        "line_id": "LINE-HOT-200C",
        "line_number": "HOT-200C",
        "nominal_bore": '6"',
        "points": [{"x": 0.0, "y": 0.0, "z": 5.0}, {"x": length_m, "y": 0.0, "z": 5.0}],
        "length_m": length_m,
        "geometry_source": "nozzle_xyz",
    }
    return g
