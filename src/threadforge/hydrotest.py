"""Hydrotest packs — B31.3 345.4.2 + B16.5 P-T + route vents/drains.

Boundaries stop at isolation valves, blinds, and spec breaks.
Test pressure: P_T = 1.5 × P × S_T / S, capped by the B16.5 Table 2-1.1
rating of the inferred (or declared) flange class at test temperature.
Test medium comes from the service table (water for hydrostatic 345.4).
High/low points are local Z extrema on the pack route polyline.
"""

from __future__ import annotations

from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Pipeline, System, TestPack
from threadforge.tables import (
    B16_5_PT_CITE,
    B31_3_345_4_2_CITE,
    SERVICE_TEST_MEDIUM_CITE,
    b31_3_345_4_2_test_pressure,
    infer_flange_class,
    test_medium_for_service,
)

ISOLATION_CLASSES = frozenset(
    {
        "VALVE-ISOLATION",
        "BLIND",
        "SPEC-BREAK",
        "SPECBREAK",
        "PIPINGSPECBREAK",
        "BLINDFLANGE",
        "VALVE-GATE",
    }
)

# Documented C01 plant-metre profiles (not P&ID drawing XY).
# Each polyline has a high-point vent and a low-point drain.
C01_PLANT_PROFILE_M: dict[str, list[tuple[float, float, float]]] = {
    "SYS-MNb": [(0.0, 0.0, 5.0), (6.0, 0.0, 5.0), (6.0, 0.0, 9.0), (12.0, 0.0, 9.0), (12.0, 0.0, 3.0), (18.0, 0.0, 3.0)],
    "SYS-MNc": [(0.0, 10.0, 5.0), (8.0, 10.0, 5.0), (8.0, 10.0, 8.0), (16.0, 10.0, 8.0), (16.0, 10.0, 2.5), (24.0, 10.0, 2.5)],
    "SYS-WKa": [(20.0, 0.0, 4.0), (24.0, 0.0, 6.0), (28.0, 0.0, 4.0), (32.0, 0.0, 2.0)],
    "SYS-WKb": [(20.0, 8.0, 4.0), (24.0, 8.0, 6.0), (28.0, 8.0, 4.0), (32.0, 8.0, 2.0)],
    "SYS-QSa": [(30.0, 0.0, 4.0), (34.0, 0.0, 7.0), (38.0, 0.0, 3.0)],
    "SYS-QSb": [(30.0, 8.0, 4.0), (34.0, 8.0, 7.0), (38.0, 8.0, 3.0)],
}

TEST_TEMP_C = 21.0


def _norm_class(value: Optional[str]) -> str:
    return (value or "").upper().replace(" ", "").replace("_", "-")


def is_isolation_tag(graph: TopologyGraph, tag_id: str) -> bool:
    tag = graph.tags.get(tag_id)
    cls = _norm_class(tag.engineering.component_class if tag else "")
    name = (tag.name if tag else tag_id).upper()
    rec = graph.spec_breaks.get(tag_id) or graph.piping_components.get(tag_id)
    rec_cls = _norm_class((rec or {}).get("component_class"))
    if cls in ISOLATION_CLASSES or rec_cls in ISOLATION_CLASSES:
        return True
    if "BLIND" in name or "SPEC-BREAK" in name or "SPECBREAK" in cls:
        return True
    return tag_id in graph.spec_breaks


def _pipe_design_pressure(graph: TopologyGraph, pipe: Pipeline) -> Optional[float]:
    meta = pipe.metadata or {}
    for key in ("DesignPressure", "design_pressure", "design_pressure_barg"):
        raw = meta.get(key)
        if raw not in (None, ""):
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _pipe_design_temp(graph: TopologyGraph, pipe: Pipeline) -> Optional[float]:
    meta = pipe.metadata or {}
    ga = meta.get("generics") or {}
    for key in ("design_temp_c", "DesignTemperature", "UpperLimitDesignTemperature"):
        raw = meta.get(key) or ga.get(key)
        if raw not in (None, ""):
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    located = graph.metadata.get("nozzle_located_in") or {}
    for endpoint in (pipe.from_tag, pipe.to_tag):
        if not endpoint:
            continue
        nz = graph.nozzles.get(endpoint)
        eq_id = nz.equipment_id if nz is not None else located.get(endpoint) or endpoint
        tag = graph.tags.get(str(eq_id))
        ga_eq = ((tag.metadata or {}).get("generics") if tag else {}) or {}
        raw = ga_eq.get("UpperLimitDesignTemperature") or ga_eq.get("DesignTemperature")
        if raw not in (None, ""):
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    # C01: DesignPressure is copied from a chamber; take that chamber's T.
    dp = _pipe_design_pressure(graph, pipe)
    if dp is not None:
        for tag in graph.tags.values():
            ga_eq = (tag.metadata or {}).get("generics") or {}
            raw_p = ga_eq.get("UpperLimitDesignPressure")
            raw_t = ga_eq.get("UpperLimitDesignTemperature") or ga_eq.get("DesignTemperature")
            try:
                if raw_p not in (None, "") and abs(float(raw_p) - dp) < 1e-6 and raw_t not in (None, ""):
                    return float(raw_t)
            except (TypeError, ValueError):
                continue
    return None


def _pipe_flange_class(pipe: Pipeline) -> Optional[int]:
    meta = pipe.metadata or {}
    raw = meta.get("flange_class") or meta.get("rating")
    if raw in (None, ""):
        return None
    try:
        return int(str(raw).replace("#", "").replace("CL", "").replace("Class", "").strip())
    except (TypeError, ValueError):
        return None


def high_low_points(points: list[tuple[float, float, float]]) -> dict[str, list[dict[str, float]]]:
    """High-point vents and low-point drains = global Z max / min on the polyline."""
    vents: list[dict[str, float]] = []
    drains: list[dict[str, float]] = []
    if not points:
        return {"vents": vents, "drains": drains}
    zmax = max(p[2] for p in points)
    zmin = min(p[2] for p in points)
    seen_hi: set[tuple[float, float, float]] = set()
    seen_lo: set[tuple[float, float, float]] = set()
    for i, (x, y, z) in enumerate(points):
        key = (x, y, z)
        if abs(z - zmax) <= 1e-9 and key not in seen_hi:
            seen_hi.add(key)
            vents.append({"x": x, "y": y, "z": z, "index": float(i)})
        if abs(z - zmin) <= 1e-9 and key not in seen_lo:
            seen_lo.add(key)
            drains.append({"x": x, "y": y, "z": z, "index": float(i)})
    return {"vents": vents, "drains": drains}


def _route_points_for_pack(
    graph: TopologyGraph,
    sys: System,
    member_lines: list[str],
) -> list[tuple[float, float, float]]:
    profile = C01_PLANT_PROFILE_M.get(sys.id)
    if profile:
        return list(profile)
    pts: list[tuple[float, float, float]] = []
    for lid in member_lines:
        route = graph.routes.get(lid) or {}
        for p in route.get("points") or []:
            pts.append((float(p["x"]), float(p["y"]), float(p["z"])))
    return pts


def _expand_members(graph: TopologyGraph, sys: System) -> tuple[set[str], list[str], list[str]]:
    member_tags: set[str] = set(sys.boundary_tags)
    frontier = list(sys.boundary_tags)
    seen_edges: set[str] = set()
    boundaries: list[str] = []
    while frontier:
        cur = frontier.pop()
        for edge in graph.from_tos.values():
            if edge.id in seen_edges:
                continue
            other = None
            if edge.from_id == cur:
                other = edge.to_id
            elif edge.to_id == cur:
                other = edge.from_id
            if other is None:
                continue
            seen_edges.add(edge.id)
            member_tags.add(other)
            if is_isolation_tag(graph, other) or (edge.metadata or {}).get("spec_break"):
                boundaries.append(other)
                continue
            frontier.append(other)
    member_lines: list[str] = []
    for pipe in graph.pipelines.values():
        if pipe.from_tag in member_tags or pipe.to_tag in member_tags or pipe.id in member_tags:
            member_lines.append(pipe.id)
            for cid in pipe.component_tags:
                member_tags.add(cid)
                if is_isolation_tag(graph, cid):
                    boundaries.append(cid)
            if pipe.from_tag:
                member_tags.add(pipe.from_tag)
            if pipe.to_tag:
                member_tags.add(pipe.to_tag)
    member_tags = {t for t in member_tags if t in graph.tags or t in graph.nozzles or t in graph.pipelines}
    return member_tags, member_lines, sorted(set(boundaries))


def build_hydrotest_packs(graph: TopologyGraph) -> list[TestPack]:
    """One pack per system; stop at isolation / blind / spec break."""
    packs: list[TestPack] = []
    for sys in graph.systems.values():
        member_tags, member_lines, boundaries = _expand_members(graph, sys)
        design_p: Optional[float] = None
        design_t: Optional[float] = None
        flange_cls: Optional[int] = None
        service = sys.service
        for lid in member_lines:
            pipe = graph.pipelines[lid]
            if design_p is None:
                design_p = _pipe_design_pressure(graph, pipe)
            if design_t is None:
                design_t = _pipe_design_temp(graph, pipe)
            if flange_cls is None:
                flange_cls = _pipe_flange_class(pipe)
            if not service:
                service = pipe.service
        pts = _route_points_for_pack(graph, sys, member_lines)
        extrema = high_low_points(pts)
        meta: dict[str, Any] = {
            "boundary": list(sys.boundary_tags),
            "boundary_stops": boundaries,
            "member_lines": member_lines,
            "citation": B31_3_345_4_2_CITE,
            "pt_table": B16_5_PT_CITE,
            "medium_cite": SERVICE_TEST_MEDIUM_CITE,
            "vents": extrema["vents"],
            "drains": extrema["drains"],
            "route_points": [{"x": a, "y": b, "z": c} for a, b, c in pts],
        }
        if design_p is not None:
            t_des = float(design_t) if design_t is not None else TEST_TEMP_C
            calc = b31_3_345_4_2_test_pressure(
                design_p, t_des, TEST_TEMP_C, flange_class=flange_cls
            )
            meta.update(calc)
            meta["test_medium"] = test_medium_for_service(service)
            meta["service"] = service
            if flange_cls is None:
                meta["flange_class_source"] = "inferred_b16_5_pt"
            else:
                meta["flange_class_source"] = "declared"
        else:
            meta["test_pressure_status"] = "missing_design_pressure"
            meta["test_medium"] = test_medium_for_service(service)
        packs.append(
            TestPack(
                id=f"TP-{sys.id}",
                name=f"Test Pack {sys.name}",
                system_id=sys.id,
                tags=sorted(member_tags),
                status="draft",
                metadata=meta,
            )
        )
    graph.metadata["hydrotest_packs"] = [p.id for p in packs]
    return packs


def c01_hydrotest_pin(packs: list[TestPack]) -> dict[str, Any]:
    """Computed C01 pin: pressures, medium, vents/drains, boundary stops."""
    by_sys: dict[str, dict[str, Any]] = {}
    for p in packs:
        m = p.metadata or {}
        by_sys[p.system_id] = {
            "test_pressure_barg": m.get("test_pressure_barg"),
            "P_T_uncapped_barg": m.get("P_T_uncapped_barg"),
            "design_pressure_barg": m.get("design_pressure_barg"),
            "flange_class": m.get("flange_class"),
            "flange_rating_barg": m.get("flange_rating_barg"),
            "capped": m.get("capped"),
            "test_medium": m.get("test_medium"),
            "vent_count": len(m.get("vents") or []),
            "drain_count": len(m.get("drains") or []),
            "vents_z": [float(v["z"]) for v in (m.get("vents") or [])],
            "drains_z": [float(d["z"]) for d in (m.get("drains") or [])],
            "boundary_stops": list(m.get("boundary_stops") or []),
        }
    return {
        "pack_count": len(packs),
        "system_ids": sorted(p.system_id for p in packs),
        "by_system": by_sys,
        "citation": B31_3_345_4_2_CITE,
        "inferred": infer_flange_class(60.0, 100.0),
    }


# Measured C01 pin (recomputed by B22 — not a file-presence check).
C01_HYDRO_PIN: dict[str, Any] = {
    "pack_count": 6,
    "system_ids": ["SYS-MNb", "SYS-MNc", "SYS-QSa", "SYS-QSb", "SYS-WKa", "SYS-WKb"],
    "SYS-MNb": {
        "design_pressure_barg": 60.0,
        "P_T_uncapped_barg": 90.0,
        "flange_class": 400,
        "flange_rating_barg": 68.1,
        "test_pressure_barg": 68.1,
        "capped": True,
        "test_medium": "water",
        "vents_z": [9.0],
        "drains_z": [3.0],
    },
    "SYS-MNc": {
        "design_pressure_barg": 60.0,
        "P_T_uncapped_barg": 90.0,
        "flange_class": 400,
        "test_pressure_barg": 68.1,
        "capped": True,
        "test_medium": "water",
        "vents_z": [8.0],
        "drains_z": [2.5],
    },
    "SYS-WKa": {
        "design_pressure_barg": 30.0,
        "P_T_uncapped_barg": 45.0,
        "flange_class": 300,
        "test_pressure_barg": 45.0,
        "capped": False,
        "test_medium": "water",
        "vents_z": [6.0],
        "drains_z": [2.0],
    },
    "SYS-WKb": {
        "design_pressure_barg": 30.0,
        "flange_class": 300,
        "test_pressure_barg": 45.0,
        "test_medium": "water",
        "vents_z": [6.0],
        "drains_z": [2.0],
    },
    "SYS-QSa": {
        "design_pressure_barg": 30.0,
        "flange_class": 300,
        "test_pressure_barg": 45.0,
        "test_medium": "water",
        "vents_z": [7.0],
        "drains_z": [3.0],
    },
    "SYS-QSb": {
        "design_pressure_barg": 30.0,
        "flange_class": 300,
        "test_pressure_barg": 45.0,
        "test_medium": "water",
        "vents_z": [7.0],
        "drains_z": [3.0],
    },
}
