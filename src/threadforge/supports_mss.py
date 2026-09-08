"""MSS SP-58 support types from route kinematics (not load-rated).

Citation: MSS SP-58 Pipe Hangers and Supports — Materials, Design, Manufacture,
Selection, Application, and Installation.

| Kinematic rule                         | Type name      | MSS SP-58 |
|----------------------------------------|----------------|-----------|
| Equipment nozzle (route ends)          | anchor         | Type 40   |
| Every N support spans on horizontal    | guide          | Type 42   |
| Insulated line interval support        | shoe           | Type 1    |
| Vertical run longer than 6 m           | spring_hanger  | Type 51   |

N = ``GUIDE_EVERY_N_SPANS`` (2). Vertical threshold = ``SPRING_VERTICAL_M`` (6.0).
``support_placeholders_engineered`` is unchanged (A09 pin).
"""

from __future__ import annotations

import math
from typing import Any, Optional

from threadforge.routing import Point3, polyline_length
from threadforge.tables import support_span_m

GUIDE_EVERY_N_SPANS = 2
SPRING_VERTICAL_M = 6.0

MSS_TYPE = {
    "anchor": "Type 40",
    "guide": "Type 42",
    "shoe": "Type 1",
    "spring_hanger": "Type 51",
}


def _lerp(a: Point3, b: Point3, t: float) -> Point3:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))


def _seg_len(a: Point3, b: Point3) -> float:
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)


def _is_vertical(a: Point3, b: Point3, tol: float = 0.15) -> bool:
    horiz = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
    vert = abs(b[2] - a[2])
    return vert > 1e-6 and horiz <= tol * max(vert, 1e-6)


def support_types_kinematic(
    points: list[Point3],
    nominal_bore: Optional[str] = None,
    insulated: bool = False,
    guide_every_n: int = GUIDE_EVERY_N_SPANS,
    spring_vertical_m: float = SPRING_VERTICAL_M,
) -> list[dict[str, Any]]:
    """Place MSS SP-58 typed supports from polyline kinematics."""
    if len(points) < 2:
        return []
    span = support_span_m(nominal_bore)
    total = polyline_length(points)
    out: list[dict[str, Any]] = []

    def _add(kind: str, xyz: Point3, station: float, note: str) -> None:
        out.append(
            {
                "id": f"MSS-{len(out)+1:03d}",
                "type": kind,
                "mss_sp58": MSS_TYPE[kind],
                "xyz": [xyz[0], xyz[1], xyz[2]],
                "station_m": round(station, 3),
                "note": note,
                "standard": "MSS SP-58",
            }
        )

    _add("anchor", points[0], 0.0, "Anchor at equipment nozzle — MSS SP-58 Type 40")
    _add("anchor", points[-1], total, "Anchor at equipment nozzle — MSS SP-58 Type 40")

    # Interval shoes / guides along developed length.
    if span > 0 and total > span * 0.5:
        next_at = span
        guide_i = 0
        dist_accum = 0.0
        for a, b in zip(points, points[1:]):
            seg = _seg_len(a, b)
            if seg < 1e-9:
                continue
            while next_at <= dist_accum + seg + 1e-9 and next_at < total - 0.25:
                t = (next_at - dist_accum) / seg
                pos = _lerp(a, b, min(1.0, max(0.0, t)))
                guide_i += 1
                if insulated:
                    _add(
                        "shoe",
                        pos,
                        next_at,
                        "Pipe shoe on insulated line — MSS SP-58 Type 1",
                    )
                if guide_i % guide_every_n == 0:
                    _add(
                        "guide",
                        pos,
                        next_at,
                        f"Guide every {guide_every_n} spans — MSS SP-58 Type 42",
                    )
                next_at += span
            dist_accum += seg

    # Spring hanger where a vertical run exceeds 6 m.
    dist_accum = 0.0
    for a, b in zip(points, points[1:]):
        seg = _seg_len(a, b)
        if _is_vertical(a, b) and abs(b[2] - a[2]) > spring_vertical_m:
            top = a if a[2] >= b[2] else b
            station = dist_accum if a[2] >= b[2] else dist_accum + seg
            _add(
                "spring_hanger",
                top,
                station,
                f"Spring hanger on vertical run {abs(b[2]-a[2]):.2f} m > {spring_vertical_m} m — MSS SP-58 Type 51",
            )
        dist_accum += seg
    return out


def type_counts(supports: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"anchor": 0, "guide": 0, "shoe": 0, "spring_hanger": 0}
    for s in supports:
        t = str(s.get("type") or "")
        if t in counts:
            counts[t] += 1
    return counts
