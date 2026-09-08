"""B15: hypothesis properties for A* clearance and segment_distance."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from threadforge.clash import segment_distance
from threadforge.routing import _point_in_aabb, route_astar

Point3 = tuple[float, float, float]


def _seg_len(a: Point3, b: Point3) -> float:
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)


def _brute_segment_distance(p1: Point3, q1: Point3, p2: Point3, q2: Point3) -> float:
    """Uniform parameter sampling; spacing ≤ 0.8 mm so the grid is within ±1 mm."""
    n1 = max(400, min(2500, int(_seg_len(p1, q1) / 0.0008) + 1))
    n2 = max(400, min(2500, int(_seg_len(p2, q2) / 0.0008) + 1))
    best = 1e18
    for i in range(n1 + 1):
        t = i / n1
        a = (p1[0] + t * (q1[0] - p1[0]), p1[1] + t * (q1[1] - p1[1]), p1[2] + t * (q1[2] - p1[2]))
        for j in range(n2 + 1):
            s = j / n2
            b = (p2[0] + s * (q2[0] - p2[0]), p2[1] + s * (q2[1] - p2[1]), p2[2] + s * (q2[2] - p2[2]))
            d = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
            if d < best:
                best = d
    return best


_coord = st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
_pt = st.tuples(_coord, _coord, _coord)


def test_segment_distance_known_near_intersect():
    """Regression: crossing segments in Y=0 (true dist 0) vs dense brute."""
    p1, q1 = (0.0, 0.0, 1.0), (2.0, 0.0, 0.0)
    p2, q2 = (0.0, 0.0, 0.0), (1.0, 0.0, 1.0)
    d1, _, _ = segment_distance(p1, q1, p2, q2)
    d2, _, _ = segment_distance(p2, q2, p1, q1)
    assert d1 >= 0 and abs(d1 - d2) <= 1e-9
    assert abs(d1 - _brute_segment_distance(p1, q1, p2, q2)) <= 0.001


@settings(max_examples=40, deadline=None)
@given(p1=_pt, q1=_pt, p2=_pt, q2=_pt)
def test_segment_distance_symmetric_nonneg_vs_brute(
    p1: Point3, q1: Point3, p2: Point3, q2: Point3
) -> None:
    d1, _, _ = segment_distance(p1, q1, p2, q2)
    d2, _, _ = segment_distance(p2, q2, p1, q1)
    assert d1 >= -1e-12
    assert abs(d1 - d2) <= 1e-9
    brute = _brute_segment_distance(p1, q1, p2, q2)
    assert abs(d1 - brute) <= 0.001  # ±1 mm


_box_lo = st.floats(min_value=2.0, max_value=6.0, allow_nan=False, allow_infinity=False)
_box_hi = st.floats(min_value=0.4, max_value=2.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=25, deadline=None)
@given(
    x=_box_lo,
    y=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    z=st.floats(min_value=4.0, max_value=6.0, allow_nan=False, allow_infinity=False),
    dx=_box_hi,
    dy=_box_hi,
    dz=_box_hi,
)
def test_astar_never_penetrates_random_aabb(
    x: float, y: float, z: float, dx: float, dy: float, dz: float
) -> None:
    box = (x, y, z, x + dx, y + dy, z + dz)
    start = (0.0, 0.0, 5.0)
    end = (10.0, 0.0, 5.0)
    # Keep start/end outside the box so A* is asked to go around, not through a nozzle.
    if _point_in_aabb(start, box) or _point_in_aabb(end, box):
        return
    res = route_astar(start, end, obstacles={"aabbs": [box], "capsules": [], "volumes": []}, grid=0.5)
    if res.get("accuracy") != "astar":
        return
    pts = res["points"]
    for a, b in zip(pts, pts[1:]):
        for i in range(1, 12):
            t = i / 12
            p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))
            if p == start or p == end:
                continue
            assert not _point_in_aabb(p, box), (p, box, pts)
