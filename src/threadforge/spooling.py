"""Shop-spool split of a PCF centreline chain.

Limits (fabrication / transport — not a piping-code stress rule):

- Developed length ≤ ``SHOP_MAX_LENGTH_M`` = 12.0 m.
- Mass ≤ ``SHOP_MAX_MASS_KG`` = 2000 kg (2 t), using ASME B36.10M kg/m
  (OD + schedule wall, ρ = 7850 kg/m³) × developed length.
- Axis-aligned AABB, after sorting the three extents, must fit inside the
  transportable envelope ``ENVELOPE_M`` = (12.0, 2.4, 2.4) m.

Envelope citation: ISO 668:2020 Table 1 type 1AA (40′) external
12 192 × 2 438 × 2 591 mm. The shop envelope 12.0 × 2.4 × 2.4 m is the
non-oversize cargo box used inside that family (road-legal flatbed).

Field welds sit at spool breaks. Shop welds sit at weldable metal joints
inside a spool. Weld numbers are ``W-<line_number>-<n>``. Each component
carries a ``SPOOL-IDENTIFIER`` ``S-<line_number>-<nn>``.

ISOGEN certification remains a WALL — one log line, structural subset only.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Discipline, Equipment, Nozzle, Pipeline, Tag
from threadforge.tables import mass_per_m, wall_thickness_mm

logger = logging.getLogger("threadforge.spooling")

SHOP_MAX_LENGTH_M = 12.0
SHOP_MAX_MASS_KG = 2000.0  # 2 t
# ISO 668:2020 Table 1 type 1AA external 12.192 × 2.438 × 2.591 m;
# shop cargo box used here: 12.0 × 2.4 × 2.4 m.
ENVELOPE_M: tuple[float, float, float] = (12.0, 2.4, 2.4)
ENVELOPE_CITE = (
    "ISO 668:2020 Table 1 type 1AA (40') external 12192×2438×2591 mm; "
    "shop envelope 12.0×2.4×2.4 m (non-oversize cargo box)"
)
LENGTH_CITE = "shop developed length ≤ 12.0 m (transportable piece)"
MASS_CITE = "shop mass ≤ 2.0 t using ASME B36.10M kg/m × developed length"

_WALL_LOGGED = False

WELDABLE_RUN = frozenset({"PIPE", "ELBOW", "REDUCER", "TEE"})
NON_WELD = frozenset({"GASKET", "VALVE", "SUPPORT", "WELD", "BOLT"})


def _wall_once() -> None:
    global _WALL_LOGGED
    if _WALL_LOGGED:
        return
    logger.warning("WALL: Autodesk ISOGEN PCF certification — shop-spool PCF is a structural subset only")
    _WALL_LOGGED = True


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))


def _aabb_dims(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not points:
        return (0.0, 0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def fits_envelope(points: list[tuple[float, float, float]], envelope: tuple[float, float, float] = ENVELOPE_M) -> bool:
    """True if sorted AABB extents fit the sorted envelope (rotation allowed)."""
    dims = sorted(_aabb_dims(points), reverse=True)
    env = sorted(envelope, reverse=True)
    return all(d <= e + 1e-9 for d, e in zip(dims, env))


def fits_shop(
    length_m: float,
    mass_kg: float,
    points: list[tuple[float, float, float]],
) -> bool:
    if length_m > SHOP_MAX_LENGTH_M + 1e-9:
        return False
    if mass_kg > SHOP_MAX_MASS_KG + 1e-9:
        return False
    return fits_envelope(points)


def is_weldable_joint(prev_kind: str, next_kind: str) -> bool:
    """Butt/WN metal joints only — not gasket, bolted flange-flange, or valve."""
    if prev_kind in NON_WELD or next_kind in NON_WELD:
        return False
    if prev_kind == "FLANGE" and next_kind == "FLANGE":
        return False
    if prev_kind in WELDABLE_RUN and next_kind in WELDABLE_RUN:
        return True
    if prev_kind in WELDABLE_RUN and next_kind == "FLANGE":
        return True
    if prev_kind == "FLANGE" and next_kind in WELDABLE_RUN:
        return True
    return False


def segment_length_m(seg: dict[str, Any]) -> float:
    kind = str(seg.get("kind") or "")
    if kind in ("WELD", "SUPPORT"):
        return 0.0
    a = seg.get("a")
    b = seg.get("b")
    if a is None or b is None:
        return 0.0
    pa = (float(a[0]), float(a[1]), float(a[2]))
    pb = (float(b[0]), float(b[1]), float(b[2]))
    if kind == "ELBOW" and seg.get("centre") is not None:
        centre = (float(seg["centre"][0]), float(seg["centre"][1]), float(seg["centre"][2]))
        r = float(seg.get("r") or _dist(pa, centre))
        ang_cs = float(seg.get("angle") or 9000)
        theta = abs(ang_cs) / 100.0 * math.pi / 180.0
        return r * theta
    return _dist(pa, pb)


def segment_points(seg: dict[str, Any]) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    for key in ("a", "b", "centre"):
        raw = seg.get(key)
        if raw is None:
            continue
        pts.append((float(raw[0]), float(raw[1]), float(raw[2])))
    return pts


def _point_on(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))


def split_pipe(seg: dict[str, Any], take_m: float) -> tuple[dict[str, Any], dict[str, Any]]:
    a = (float(seg["a"][0]), float(seg["a"][1]), float(seg["a"][2]))
    b = (float(seg["b"][0]), float(seg["b"][1]), float(seg["b"][2]))
    full = _dist(a, b)
    t = 1.0 if full < 1e-12 else max(0.0, min(1.0, take_m / full))
    mid = _point_on(a, b, t)
    head = dict(seg)
    tail = dict(seg)
    head["a"], head["b"] = a, mid
    tail["a"], tail["b"] = mid, b
    return head, tail


def _empty_spool(spool_id: str, line_id: str, line_number: str) -> dict[str, Any]:
    return {
        "spool_id": spool_id,
        "line_id": line_id,
        "line_number": line_number,
        "length_m": 0.0,
        "mass_kg": 0.0,
        "points": [],
        "cut_lengths_m": [],
        "axis_points": [],
        "fittings": [],
        "weld_ids": [],
        "field_weld_ids": [],
        "shop_weld_ids": [],
        "oversize": False,
    }


def apply_spooling(
    chain: list[dict[str, Any]],
    *,
    line_id: str,
    line_number: str,
    nominal_bore: Optional[str],
    schedule: str = "40",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stamp SPOOL-IDENTIFIER, insert shop/field WELD, enforce shop limits.

    Returns ``(new_chain, report)``. ``report`` carries pinned-count fields.
    """
    _wall_once()
    kg_m = mass_per_m(nominal_bore, schedule)
    wall_mm = wall_thickness_mm(nominal_bore, schedule)
    out: list[dict[str, Any]] = []
    spools: list[dict[str, Any]] = []
    welds: list[dict[str, Any]] = []
    weld_n = 0
    spool_n = 0
    prev_kind: Optional[str] = None

    def _sid(n: int) -> str:
        return f"S-{line_number}-{n:02d}"

    def _wid(n: int) -> str:
        return f"W-{line_number}-{n}"

    def _open() -> dict[str, Any]:
        nonlocal spool_n
        spool_n += 1
        sp = _empty_spool(_sid(spool_n), line_id, line_number)
        spools.append(sp)
        return sp

    def _add_weld(
        xyz: tuple[float, float, float],
        shop_field: str,
        spool: dict[str, Any],
        bore: Any = None,
    ) -> dict[str, Any]:
        nonlocal weld_n
        weld_n += 1
        wid = _wid(weld_n)
        rec: dict[str, Any] = {
            "kind": "WELD",
            "a": xyz,
            "b": xyz,
            "skey": "WF" if shop_field == "field" else "WW",
            "weld_id": wid,
            "shop_field": shop_field,
            "weld_type": "BW",
            "spool_id": spool["spool_id"],
            "line_id": line_id,
            "line_number": line_number,
            "nominal_bore": nominal_bore,
            "wall_mm": wall_mm,
            "xyz": xyz,
            "_bore_a": bore,
            "_bore_b": bore,
        }
        out.append(rec)
        welds.append(
            {
                "weld_id": wid,
                "line_id": line_id,
                "line_number": line_number,
                "spool_id": spool["spool_id"],
                "shop_field": shop_field,
                "weld_type": "BW",
                "nominal_bore": nominal_bore,
                "wall_mm": wall_mm,
                "xyz": xyz,
            }
        )
        spool["weld_ids"].append(wid)
        if shop_field == "field":
            spool["field_weld_ids"].append(wid)
        else:
            spool["shop_weld_ids"].append(wid)
        return rec

    def _commit_piece(piece: dict[str, Any], spool: dict[str, Any], sl: float, sm: float) -> None:
        nonlocal prev_kind
        item = dict(piece)
        item["spool_id"] = spool["spool_id"]
        kind = str(item.get("kind") or "")
        if prev_kind and is_weldable_joint(prev_kind, kind):
            xyz = (float(item["a"][0]), float(item["a"][1]), float(item["a"][2]))
            _add_weld(xyz, "shop", spool, bore=item.get("_bore_a"))
        out.append(item)
        spool["length_m"] += sl
        spool["mass_kg"] += sm
        spool["points"].extend(segment_points(item))
        if item.get("a") is not None:
            pa = (float(item["a"][0]), float(item["a"][1]), float(item["a"][2]))
            if not spool["axis_points"] or _dist(spool["axis_points"][-1], pa) > 1e-9:
                spool["axis_points"].append(pa)
        if item.get("b") is not None and kind != "WELD":
            pb = (float(item["b"][0]), float(item["b"][1]), float(item["b"][2]))
            if not spool["axis_points"] or _dist(spool["axis_points"][-1], pb) > 1e-9:
                spool["axis_points"].append(pb)
        if kind == "PIPE":
            spool["cut_lengths_m"].append(sl)
        elif kind not in ("WELD", "SUPPORT", "PIPE"):
            spool["fittings"].append(
                {"kind": kind, "tag": item.get("tag") or item.get("item_code"), "length_m": sl}
            )
        prev_kind = kind

    current = _open()
    for seg in chain:
        kind = str(seg.get("kind") or "")
        if kind == "SUPPORT":
            item = dict(seg)
            item["spool_id"] = current["spool_id"]
            out.append(item)
            continue
        sl = segment_length_m(seg)
        sm = kg_m * sl
        trial_pts = list(current["points"]) + segment_points(seg)
        if fits_shop(current["length_m"] + sl, current["mass_kg"] + sm, trial_pts):
            _commit_piece(seg, current, sl, sm)
            continue
        if kind == "PIPE":
            remaining = sl
            cursor = dict(seg)
            while remaining > 1e-9:
                take = _max_take_pipe(cursor, current, kg_m)
                if take < 1e-6:
                    if current["length_m"] <= 1e-12 and not current["points"]:
                        # empty spool still cannot take any — force-add a sliver then break
                        take = min(remaining, SHOP_MAX_LENGTH_M)
                        current["oversize"] = True
                    else:
                        xyz = (float(cursor["a"][0]), float(cursor["a"][1]), float(cursor["a"][2]))
                        _add_weld(xyz, "field", current, bore=cursor.get("_bore_a"))
                        prev_kind = "WELD"
                        current = _open()
                        continue
                if take + 1e-9 >= remaining:
                    _commit_piece(cursor, current, remaining, kg_m * remaining)
                    remaining = 0.0
                else:
                    head, tail = split_pipe(cursor, take)
                    _commit_piece(head, current, take, kg_m * take)
                    xyz = (float(head["b"][0]), float(head["b"][1]), float(head["b"][2]))
                    _add_weld(xyz, "field", current, bore=cursor.get("_bore_a"))
                    prev_kind = "WELD"
                    current = _open()
                    cursor = tail
                    remaining = segment_length_m(tail)
            continue
        # unsplittable fitting — close current (if it has content) and start a new spool
        if current["length_m"] > 1e-12 or current["points"]:
            xyz = (float(seg["a"][0]), float(seg["a"][1]), float(seg["a"][2]))
            _add_weld(xyz, "field", current, bore=seg.get("_bore_a"))
            prev_kind = "WELD"
            current = _open()
        trial_pts = segment_points(seg)
        if not fits_shop(sl, sm, trial_pts):
            current["oversize"] = True
        _commit_piece(seg, current, sl, sm)

    if spools and spools[-1]["length_m"] <= 1e-12 and not spools[-1]["points"] and not spools[-1]["weld_ids"]:
        spools.pop()
        spool_n = len(spools)

    report = {
        "line_id": line_id,
        "line_number": line_number,
        "nominal_bore": nominal_bore,
        "schedule": schedule,
        "kg_m": kg_m,
        "wall_mm": wall_mm,
        "spool_count": len(spools),
        "weld_count": len(welds),
        "field_weld_count": sum(1 for w in welds if w["shop_field"] == "field"),
        "shop_weld_count": sum(1 for w in welds if w["shop_field"] == "shop"),
        "spools": spools,
        "welds": welds,
        "limits": {
            "max_length_m": SHOP_MAX_LENGTH_M,
            "max_mass_kg": SHOP_MAX_MASS_KG,
            "envelope_m": list(ENVELOPE_M),
            "length_cite": LENGTH_CITE,
            "mass_cite": MASS_CITE,
            "envelope_cite": ENVELOPE_CITE,
        },
    }
    return out, report


def _max_take_pipe(seg: dict[str, Any], current: dict[str, Any], kg_m: float) -> float:
    a = (float(seg["a"][0]), float(seg["a"][1]), float(seg["a"][2]))
    b = (float(seg["b"][0]), float(seg["b"][1]), float(seg["b"][2]))
    sl = _dist(a, b)
    if sl < 1e-12:
        return 0.0
    lo, hi = 0.0, sl
    best = 0.0
    for _ in range(48):
        mid = (lo + hi) / 2.0
        head_b = _point_on(a, b, mid / sl)
        trial_len = float(current["length_m"]) + mid
        trial_mass = float(current["mass_kg"]) + mid * kg_m
        trial_pts = list(current["points"]) + [a, head_b]
        if fits_shop(trial_len, trial_mass, trial_pts):
            best = mid
            lo = mid
        else:
            hi = mid
    return best


def limits_ok(report: dict[str, Any]) -> bool:
    for sp in report.get("spools") or []:
        if sp.get("oversize"):
            return False
        if float(sp["length_m"]) > SHOP_MAX_LENGTH_M + 1e-6:
            return False
        if float(sp["mass_kg"]) > SHOP_MAX_MASS_KG + 1e-6:
            return False
        if not fits_envelope(list(sp.get("points") or [])):
            return False
    return True


def _crafted(
    line_id: str,
    line_number: str,
    points: list[tuple[float, float, float]],
    bore: str,
    schedule: str = "40",
) -> TopologyGraph:
    g = TopologyGraph()
    a, b = points[0], points[-1]
    g.equipment[f"{line_id}-A"] = Equipment(id=f"{line_id}-A", tag=f"{line_id}-A", nozzles=[f"{line_id}-NA"])
    g.equipment[f"{line_id}-B"] = Equipment(id=f"{line_id}-B", tag=f"{line_id}-B", nozzles=[f"{line_id}-NB"])
    g.nozzles[f"{line_id}-NA"] = Nozzle(
        id=f"{line_id}-NA", tag="N", equipment_id=f"{line_id}-A", x=a[0], y=a[1], z=a[2]
    )
    g.nozzles[f"{line_id}-NB"] = Nozzle(
        id=f"{line_id}-NB", tag="N", equipment_id=f"{line_id}-B", x=b[0], y=b[1], z=b[2]
    )
    length = sum(_dist(p, q) for p, q in zip(points, points[1:]))
    tag_id = f"{line_id}-T"
    g.tags[tag_id] = Tag(id=tag_id, name=tag_id, discipline=Discipline.PIP)
    g.pipelines[line_id] = Pipeline(
        id=line_id,
        line_number=line_number,
        from_tag=f"{line_id}-NA",
        to_tag=f"{line_id}-NB",
        nominal_bore=bore,
        service="PROCESS",
        material="CS",
        component_tags=[tag_id],
        metadata={"schedule": schedule},
    )
    g.routes[line_id] = {
        "line_id": line_id,
        "line_number": line_number,
        "nominal_bore": bore,
        "from": f"{line_id}-NA",
        "to": f"{line_id}-NB",
        "points": [{"x": p[0], "y": p[1], "z": p[2]} for p in points],
        "length_m": length,
        "geometry_source": "nozzle_xyz",
    }
    return g


def crafted_straight_30m() -> TopologyGraph:
    """6″ Sch40 × 30 m — length limit → three shop spools (12+12+6)."""
    return _crafted("LINE-CRAFT-30M", "CRAFT-30M", [(0.0, 0.0, 5.0), (30.0, 0.0, 5.0)], '6"')


def crafted_envelope_u() -> TopologyGraph:
    """3 m × 3 m U in plan — second leg exceeds 2.4 m envelope width."""
    return _crafted(
        "LINE-CRAFT-ENV",
        "CRAFT-ENV",
        [(0.0, 0.0, 5.0), (3.0, 0.0, 5.0), (3.0, 3.0, 5.0)],
        '4"',
    )


def crafted_mass_24in() -> TopologyGraph:
    """NPS 24 Sch40 × 10 m — B36.10 mass/m × 10 m > 2 t, split on mass."""
    return _crafted("LINE-CRAFT-24", "CRAFT-24", [(0.0, 0.0, 2.0), (10.0, 0.0, 2.0)], '24"')
