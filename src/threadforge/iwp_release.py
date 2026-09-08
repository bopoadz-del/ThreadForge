"""Constraint-based IWP release (AWP).

Constraints are data (not sticky flags):
- materials_on_site — MTO quantities received ≥ required
- drawings_ifc — drawing maturity is IFC
- scaffold — scaffold ticket present
- permit — work permit present

``release_ready`` is the conjunction. Look-ahead (released_only) lists
only IWPs that compute True.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import MaturityLevel, WorkPackage, WPType
from threadforge.mto import build_mto

CONSTRAINT_KEYS = ("materials_on_site", "drawings_ifc", "scaffold", "permit")


def materials_on_site(graph: TopologyGraph, iwp: WorkPackage) -> bool:
    """True when MTO for this IWP is present and a received flag covers it."""
    meta = iwp.metadata or {}
    if "materials_on_site" in meta:
        return bool(meta["materials_on_site"])
    received = meta.get("mto_received_kg")
    required = meta.get("weight_kg")
    if received is not None and required is not None:
        try:
            return float(received) + 1e-9 >= float(required)
        except (TypeError, ValueError):
            return False
    mto = graph.metadata.get("mto") or {}
    per_iwp = {row.get("iwp_id"): row for row in (mto.get("per_iwp") or [])}
    row = per_iwp.get(iwp.id)
    if row and meta.get("mto_received") is True:
        return True
    return False


def drawings_at_ifc(iwp: WorkPackage, drawing_maturity: Optional[str] = None) -> bool:
    meta = iwp.metadata or {}
    if "drawings_ifc" in meta:
        return bool(meta["drawings_ifc"])
    level = drawing_maturity or meta.get("drawing_maturity") or meta.get("maturity")
    return str(level) == MaturityLevel.IFC.value


def constraint_record(
    graph: TopologyGraph,
    iwp: WorkPackage,
    drawing_maturity: Optional[str] = None,
) -> dict[str, bool]:
    meta = iwp.metadata or {}
    rec = {
        "materials_on_site": materials_on_site(graph, iwp),
        "drawings_ifc": drawings_at_ifc(iwp, drawing_maturity),
        "scaffold": bool(meta.get("scaffold", meta.get("scaffold_ready", False))),
        "permit": bool(meta.get("permit", meta.get("permit_ready", False))),
    }
    return rec


def release_ready(
    graph: TopologyGraph,
    iwp: WorkPackage,
    drawing_maturity: Optional[str] = None,
) -> bool:
    rec = constraint_record(graph, iwp, drawing_maturity)
    return all(rec[k] for k in CONSTRAINT_KEYS)


def apply_iwp_release(
    graph: TopologyGraph,
    drawing_maturity: Optional[str] = None,
) -> dict[str, Any]:
    """Stamp constraints + release_ready on every IWP. Returns pin-shaped summary."""
    if "mto" not in graph.metadata:
        try:
            graph.metadata["mto"] = build_mto(graph)
        except Exception:
            graph.metadata["mto"] = {}
    released: list[str] = []
    blocked: list[str] = []
    rows: list[dict[str, Any]] = []
    for wp in graph.work_packages.values():
        if wp.wp_type != WPType.IWP:
            continue
        rec = constraint_record(graph, wp, drawing_maturity)
        ready = all(rec[k] for k in CONSTRAINT_KEYS)
        wp.metadata = dict(wp.metadata or {})
        wp.metadata["constraints"] = rec
        wp.metadata["release_ready"] = ready
        wp.status = "released" if ready else "planned"
        row = {"iwp_id": wp.id, "release_ready": ready, **rec}
        rows.append(row)
        if ready:
            released.append(wp.id)
        else:
            blocked.append(wp.id)
    summary = {
        "iwp_count": len(rows),
        "released": sorted(released),
        "blocked": sorted(blocked),
        "released_count": len(released),
        "rows": rows,
    }
    graph.metadata["iwp_release"] = summary
    return summary


def crafted_release_graph() -> TopologyGraph:
    """Five IWPs with pinned constraint combinations."""
    g = TopologyGraph()

    def _iwp(iwp_id: str, **flags: bool) -> WorkPackage:
        wp = WorkPackage(
            id=iwp_id,
            name=iwp_id,
            wp_type=WPType.IWP,
            tags=[iwp_id],
            status="planned",
            metadata={
                "materials_on_site": flags.get("materials_on_site", False),
                "drawings_ifc": flags.get("drawings_ifc", False),
                "scaffold": flags.get("scaffold", False),
                "permit": flags.get("permit", False),
                "weight_kg": 100.0,
            },
        )
        wp.start = date(2027, 3, 5)
        wp.finish = date(2027, 3, 18)
        g.add_work_package(wp)
        return wp

    _iwp("IWP-REL-1", materials_on_site=True, drawings_ifc=True, scaffold=True, permit=True)
    _iwp("IWP-REL-2", materials_on_site=False, drawings_ifc=True, scaffold=True, permit=True)
    _iwp("IWP-REL-3", materials_on_site=True, drawings_ifc=False, scaffold=True, permit=True)
    _iwp("IWP-REL-4", materials_on_site=True, drawings_ifc=True, scaffold=False, permit=True)
    _iwp("IWP-REL-5", materials_on_site=True, drawings_ifc=True, scaffold=True, permit=False)
    return g


IWP_RELEASE_PIN = {
    "released": ["IWP-REL-1"],
    "blocked": ["IWP-REL-2", "IWP-REL-3", "IWP-REL-4", "IWP-REL-5"],
    "released_count": 1,
    "iwp_count": 5,
}
