"""Pipe-rack volumes, service → tier table, and A* preferred elevations.

Documented table: docs/rack_tiers.md
Process high / utility mid / drains low (PIP / typical EPC rack practice).
"""

from __future__ import annotations

from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import DesignVolume, Equipment, Nozzle, Pipeline

# Service class → rack tier. docs/rack_tiers.md
PROCESS_SERVICES = frozenset({"PROCESS", "FEED", "GAS", "HC", "OIL", "PROD", "PRODUCTION", "HYDROCARBON"})
UTILITY_SERVICES = frozenset({"UTILITY", "CW", "CWS", "CWR", "IA", "N2", "STEAM", "HS", "LS", "PW", "WW", "AIR"})
DRAIN_SERVICES = frozenset({"DRAIN", "SEWER", "VENT", "OD", "CD", "CLOSED_DRAIN"})

TIER_HIGH = "high"
TIER_MID = "mid"
TIER_LOW = "low"

# Default elevations (m) when a rack volume does not override.
DEFAULT_TIER_Z: dict[str, float] = {
    TIER_HIGH: 10.0,
    TIER_MID: 7.0,
    TIER_LOW: 4.0,
}

# Rich fixture pin (service-table assignment; not a path-shape pin).
RICH_TIER_PIN: dict[str, str] = {
    "LINE-200-P-1001": TIER_HIGH,  # FEED → process
    "LINE-200-P-1002": TIER_HIGH,  # FEED → process
    "LINE-210-G-2001": TIER_HIGH,  # GAS → process
    "LINE-200-D-1010": TIER_LOW,  # DRAIN
}

SERVICE_TIER_TABLE: dict[str, str] = {
    **{s: TIER_HIGH for s in PROCESS_SERVICES},
    **{s: TIER_MID for s in UTILITY_SERVICES},
    **{s: TIER_LOW for s in DRAIN_SERVICES},
}


def classify_service(service: Optional[str]) -> str:
    """Return process | utility | drain (default process)."""
    key = (service or "").strip().upper()
    if key in DRAIN_SERVICES:
        return "drain"
    if key in UTILITY_SERVICES:
        return "utility"
    return "process"


def assign_rack_tier(service: Optional[str]) -> str:
    """Map a line service to high / mid / low (docs/rack_tiers.md)."""
    key = (service or "").strip().upper()
    if key in SERVICE_TIER_TABLE:
        return SERVICE_TIER_TABLE[key]
    return TIER_HIGH if classify_service(key) == "process" else TIER_MID


def rack_config(graph: TopologyGraph) -> dict[str, Any]:
    cfg = graph.metadata.get("rack")
    if isinstance(cfg, dict):
        return cfg
    return {}


def rack_tier_z(graph: TopologyGraph, tier: str) -> float:
    cfg = rack_config(graph)
    raw_tiers = cfg.get("tiers")
    tiers: dict[str, Any] = raw_tiers if isinstance(raw_tiers, dict) else {}
    if tier in tiers:
        return float(tiers[tier])
    return float(DEFAULT_TIER_Z[tier])


def rack_xy_aabb(graph: TopologyGraph) -> Optional[tuple[float, float, float, float]]:
    """Return (xmin, ymin, xmax, ymax) of the active rack volume."""
    cfg = rack_config(graph)
    vid = cfg.get("volume_id")
    vol: Optional[DesignVolume] = None
    if vid and vid in graph.volumes:
        vol = graph.volumes[vid]
    elif "VOL-RACK" in graph.volumes:
        vol = graph.volumes["VOL-RACK"]
    if vol is None:
        return None
    return (vol.xmin, vol.ymin, vol.xmax, vol.ymax)


def assign_route_tier(graph: TopologyGraph, service: Optional[str]) -> dict[str, Any]:
    tier = assign_rack_tier(service)
    return {
        "rack_tier": tier,
        "rack_tier_z": rack_tier_z(graph, tier),
        "rack_service_class": classify_service(service),
        "rack_table": "docs/rack_tiers.md",
    }


def rich_tier_assignment(graph: TopologyGraph) -> dict[str, str]:
    """Computed service→tier map for every pipeline (used to pin the rich fixture)."""
    return {lid: assign_rack_tier(p.service) for lid, p in graph.pipelines.items()}


def three_service_rack_graph() -> TopologyGraph:
    """Crafted rack: process / utility / drain share XY, prefer distinct tiers."""
    g = TopologyGraph()
    g.volumes["VOL-RACK"] = DesignVolume(
        id="VOL-RACK",
        name="Crafted rack",
        xmin=2.0,
        ymin=0.0,
        zmin=3.0,
        xmax=18.0,
        ymax=8.0,
        zmax=12.0,
    )
    g.metadata["rack"] = {
        "volume_id": "VOL-RACK",
        "tiers": dict(DEFAULT_TIER_Z),
        "enforce": True,
        "tier_weight": 4.0,
    }
    lines = [
        ("L-RACK-P", "RACK-P", "PROCESS", (0.0, 2.0, 7.0), (20.0, 2.0, 7.0), '4"'),
        ("L-RACK-U", "RACK-U", "UTILITY", (0.0, 4.0, 7.0), (20.0, 4.0, 7.0), '3"'),
        ("L-RACK-D", "RACK-D", "DRAIN", (0.0, 6.0, 7.0), (20.0, 6.0, 7.0), '3"'),
    ]
    for i, (lid, lnum, svc, start, end, bore) in enumerate(lines, start=1):
        ea, eb = f"EQ-R{i}A", f"EQ-R{i}B"
        na, nb = f"{ea}-N", f"{eb}-N"
        g.equipment[ea] = Equipment(id=ea, tag=ea, nozzles=[na], volume_id="VOL-RACK")
        g.equipment[eb] = Equipment(id=eb, tag=eb, nozzles=[nb], volume_id="VOL-RACK")
        g.nozzles[na] = Nozzle(id=na, tag="N", equipment_id=ea, x=start[0], y=start[1], z=start[2])
        g.nozzles[nb] = Nozzle(id=nb, tag="N", equipment_id=eb, x=end[0], y=end[1], z=end[2])
        g.pipelines[lid] = Pipeline(
            id=lid, line_number=lnum, from_tag=na, to_tag=nb, nominal_bore=bore, service=svc
        )
    return g


def median_z_in_rack(
    points: list[dict[str, float]],
    xy: tuple[float, float, float, float],
    step: float = 0.5,
) -> Optional[float]:
    """Median Z of samples along the polyline that sit inside the rack XY."""
    zs: list[float] = []
    pts = [(float(p["x"]), float(p["y"]), float(p["z"])) for p in points]
    for a, b in zip(pts, pts[1:]):
        leng = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
        n = max(1, int(leng / step))
        for i in range(n + 1):
            t = i / n
            x = a[0] + t * (b[0] - a[0])
            y = a[1] + t * (b[1] - a[1])
            z = a[2] + t * (b[2] - a[2])
            if xy[0] <= x <= xy[2] and xy[1] <= y <= xy[3]:
                zs.append(z)
    if not zs:
        return None
    zs.sort()
    return zs[len(zs) // 2]
