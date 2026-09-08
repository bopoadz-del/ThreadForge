"""B21 — material take-off at spool, line, IWP, and WP levels.

Quantities (cited tables):
- pipe m, kg — developed length × ASME B36.10M kg/m (ρ = 7850 kg/m³)
- fittings count — non-PIPE/WELD/SUPPORT components on the spool
- flanges / bolts / gaskets — B16.5 bolt count per flange pair
- supports by MSS SP-58 type
- paint / insulation m² — π × OD (or OD+2t_ins) × length

Three-level totals (spool → line → IWP/WP) reconcile within ±0.1 %.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Discipline, WPType
from threadforge.tables import flange_bolts, mass_per_m, od_mm

RECONCILE_TOL = 0.001  # ±0.1 %


def _aid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _blank_qty() -> dict[str, Any]:
    return {
        "pipe_m": 0.0,
        "pipe_kg": 0.0,
        "fittings_count": 0,
        "flanges": 0,
        "bolts": 0,
        "gaskets": 0,
        "supports": {"anchor": 0, "guide": 0, "shoe": 0, "spring_hanger": 0, "other": 0},
        "paint_m2": 0.0,
        "insulation_m2": 0.0,
    }


def _add(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst["pipe_m"] += float(src["pipe_m"])
    dst["pipe_kg"] += float(src["pipe_kg"])
    dst["fittings_count"] += int(src["fittings_count"])
    dst["flanges"] += int(src["flanges"])
    dst["bolts"] += int(src["bolts"])
    dst["gaskets"] += int(src["gaskets"])
    for k in dst["supports"]:
        dst["supports"][k] += int((src.get("supports") or {}).get(k) or 0)
    dst["paint_m2"] += float(src["paint_m2"])
    dst["insulation_m2"] += float(src["insulation_m2"])


def _close(q: dict[str, Any]) -> dict[str, Any]:
    out = dict(q)
    out["pipe_m"] = round(float(q["pipe_m"]), 6)
    out["pipe_kg"] = round(float(q["pipe_kg"]), 6)
    out["paint_m2"] = round(float(q["paint_m2"]), 6)
    out["insulation_m2"] = round(float(q["insulation_m2"]), 6)
    out["supports"] = dict(q["supports"])
    return out


def _rel_err(a: float, b: float) -> float:
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / scale


def _assign_line_wp(graph: TopologyGraph, line_id: str) -> tuple[Optional[str], Optional[str]]:
    """Map a line to (iwp_id, cwp_id) via from/to tags and PIP discipline."""
    pipe = graph.pipelines.get(line_id)
    if pipe is None:
        return None, None
    tags = set(pipe.component_tags)
    if pipe.from_tag:
        tags.add(pipe.from_tag)
    if pipe.to_tag:
        tags.add(pipe.to_tag)
    iwp_id: Optional[str] = None
    cwp_id: Optional[str] = None
    for wp in graph.work_packages.values():
        if wp.discipline != Discipline.PIP:
            continue
        if not tags.intersection(wp.tags):
            # volume fallback: equipment of from_tag
            continue
        if wp.wp_type == WPType.IWP and iwp_id is None:
            iwp_id = wp.id
            cwp_id = (wp.metadata or {}).get("parent_cwp") or cwp_id
        if wp.wp_type == WPType.CWP and cwp_id is None:
            cwp_id = wp.id
    if iwp_id is None:
        for wp in graph.work_packages.values():
            if wp.wp_type == WPType.IWP and wp.discipline == Discipline.PIP:
                iwp_id = wp.id
                cwp_id = (wp.metadata or {}).get("parent_cwp") or cwp_id
                break
    if cwp_id is None:
        for wp in graph.work_packages.values():
            if wp.wp_type == WPType.CWP and wp.discipline == Discipline.PIP:
                cwp_id = wp.id
                break
    return iwp_id, cwp_id


def _spool_qty(
    spool: dict[str, Any],
    *,
    bore: Optional[str],
    schedule: str,
    insulation_mm: float,
    supports: list[dict[str, Any]],
    n_flange: int,
) -> dict[str, Any]:
    q = _blank_qty()
    length = float(spool.get("length_m") or 0.0)
    kg_m = mass_per_m(bore, schedule)
    q["pipe_m"] = length
    q["pipe_kg"] = length * kg_m
    q["fittings_count"] = len(spool.get("fittings") or [])
    q["flanges"] = n_flange
    bolts, _dia = flange_bolts(bore, 150)
    pairs = max(n_flange // 2, 1 if n_flange else 0)
    q["bolts"] = pairs * bolts
    q["gaskets"] = pairs
    od = od_mm(bore) / 1000.0
    q["paint_m2"] = math.pi * od * length
    if insulation_mm > 0:
        q["insulation_m2"] = math.pi * (od + 2.0 * insulation_mm / 1000.0) * length
    for s in supports:
        kind = str(s.get("kind") or s.get("type") or "other")
        if kind not in q["supports"]:
            kind = "other"
        q["supports"][kind] += 1
    return q


def build_mto(graph: TopologyGraph) -> dict[str, Any]:
    from threadforge.generators import build_work_packages, get_spool_report, write_pcf_text

    if not graph.work_packages:
        build_work_packages(graph)

    per_spool: list[dict[str, Any]] = []
    per_line: dict[str, dict[str, Any]] = {}
    per_iwp: dict[str, dict[str, Any]] = {}
    per_wp: dict[str, dict[str, Any]] = {}

    for lid, pipe in graph.pipelines.items():
        if "spools" not in (graph.routes.get(lid) or {}):
            write_pcf_text(graph, lid)
        rep = get_spool_report(graph, lid)
        schedule = str((pipe.metadata or {}).get("schedule") or "40")
        ins = 0.0
        for key in ("insulation_mm", "InsulationThickness"):
            raw = (pipe.metadata or {}).get(key)
            if raw not in (None, ""):
                try:
                    ins = float(raw)
                    break
                except (TypeError, ValueError):
                    continue
        route = graph.routes.get(lid) or {}
        supports = list(route.get("supports_mss") or route.get("supports") or [])
        n_flange = sum(
            1
            for cid in pipe.component_tags
            if "FLG" in cid.upper()
            or "FLANGE" in cid.upper()
            or (
                cid in graph.tags
                and (graph.tags[cid].engineering.component_class or "").upper().startswith("FLANGE")
            )
        )
        iwp_id, cwp_id = _assign_line_wp(graph, lid)
        line_q = _blank_qty()
        spools = list(rep.get("spools") or [])
        used_sup: set[int] = set()
        for i, sp in enumerate(spools):
            take_fl = n_flange if i == 0 else 0
            take_sup: list[dict[str, Any]] = []
            pts = list(sp.get("points") or [])
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                zs = [p[2] for p in pts]
                bb = (
                    min(xs) - 0.15,
                    min(ys) - 0.15,
                    min(zs) - 0.15,
                    max(xs) + 0.15,
                    max(ys) + 0.15,
                    max(zs) + 0.15,
                )
            else:
                bb = None
            for si, s in enumerate(supports):
                if si in used_sup:
                    continue
                xyz = s.get("xyz") or s.get("point")
                if xyz is None:
                    continue
                x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
                inside = bb is None or (bb[0] <= x <= bb[3] and bb[1] <= y <= bb[4] and bb[2] <= z <= bb[5])
                if inside or (i == len(spools) - 1):
                    take_sup.append(s)
                    used_sup.add(si)
            q = _spool_qty(
                sp,
                bore=pipe.nominal_bore,
                schedule=schedule,
                insulation_mm=ins,
                supports=take_sup,
                n_flange=take_fl,
            )
            row = {
                "level": "spool",
                "id": sp.get("spool_id"),
                "line_id": lid,
                "line_number": pipe.line_number,
                "iwp_id": iwp_id,
                "wp_id": cwp_id,
                **_close(q),
            }
            per_spool.append(row)
            _add(line_q, q)
        per_line[lid] = {
            "level": "line",
            "id": lid,
            "line_number": pipe.line_number,
            "iwp_id": iwp_id,
            "wp_id": cwp_id,
            **_close(line_q),
        }
        if iwp_id is None:
            iwp_id = "IWP-UNASSIGNED"
            per_line[lid]["iwp_id"] = iwp_id
            for row in per_spool:
                if row["line_id"] == lid:
                    row["iwp_id"] = iwp_id
        if cwp_id is None:
            cwp_id = "WP-UNASSIGNED"
            per_line[lid]["wp_id"] = cwp_id
            for row in per_spool:
                if row["line_id"] == lid:
                    row["wp_id"] = cwp_id
        per_iwp.setdefault(iwp_id, {**_blank_qty(), "level": "iwp", "id": iwp_id})
        _add(per_iwp[iwp_id], line_q)
        per_wp.setdefault(cwp_id, {**_blank_qty(), "level": "wp", "id": cwp_id})
        _add(per_wp[cwp_id], line_q)

    def _sum(rows: list[dict[str, Any]], key: str) -> float:
        return sum(float(r.get(key) or 0.0) for r in rows)

    spool_m = _sum(per_spool, "pipe_m")
    line_m = _sum(list(per_line.values()), "pipe_m")
    iwp_m = _sum([_close(v) for v in per_iwp.values()], "pipe_m")
    wp_m = _sum([_close(v) for v in per_wp.values()], "pipe_m")
    spool_kg = _sum(per_spool, "pipe_kg")
    line_kg = _sum(list(per_line.values()), "pipe_kg")
    iwp_kg = _sum([_close(v) for v in per_iwp.values()], "pipe_kg")
    wp_kg = _sum([_close(v) for v in per_wp.values()], "pipe_kg")

    recon = {
        "pipe_m": {
            "spool": spool_m,
            "line": line_m,
            "iwp": iwp_m,
            "wp": wp_m,
            "spool_vs_line": _rel_err(spool_m, line_m),
            "line_vs_iwp": _rel_err(line_m, iwp_m),
            "line_vs_wp": _rel_err(line_m, wp_m),
        },
        "pipe_kg": {
            "spool": spool_kg,
            "line": line_kg,
            "iwp": iwp_kg,
            "wp": wp_kg,
            "spool_vs_line": _rel_err(spool_kg, line_kg),
            "line_vs_iwp": _rel_err(line_kg, iwp_kg),
            "line_vs_wp": _rel_err(line_kg, wp_kg),
        },
    }
    ok = all(
        recon[k][cmp] <= RECONCILE_TOL
        for k in ("pipe_m", "pipe_kg")
        for cmp in ("spool_vs_line", "line_vs_iwp", "line_vs_wp")
    )
    return {
        "per_spool": per_spool,
        "per_line": list(per_line.values()),
        "per_iwp": [_close(v) for v in per_iwp.values()],
        "per_wp": [_close(v) for v in per_wp.values()],
        "reconcile": recon,
        "ok": ok,
        "tol": RECONCILE_TOL,
    }


def export_mto(graph: TopologyGraph, output_dir: Optional[Any] = None) -> dict[str, Any]:
    import json
    from pathlib import Path

    payload = build_mto(graph)
    if output_dir is not None:
        d = Path(output_dir) / "mto"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "mto.json"
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["path"] = str(p)
    return payload
