"""FEED / L1..L4 / DD / IFC maturity gates."""

from __future__ import annotations

from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import (
    MATURITY_ORDER,
    JobPipeline,
    JobStage,
    MaturityLevel,
    StageStatus,
)


def maturity_index(level: MaturityLevel) -> int:
    return MATURITY_ORDER.index(level)


def meets_or_exceeds(current: MaturityLevel, required: MaturityLevel) -> bool:
    return maturity_index(current) >= maturity_index(required)


def ifc_issue_gates(graph: TopologyGraph) -> dict[str, Any]:
    """B28 data gates: fabricated, unmatched OPC, spec breaks, clash, flex, pressure."""
    from threadforge.clash import clash_check
    from threadforge.flexibility import STATUS_PASS, screen_graph
    from threadforge.spec_break import validate_spec_breaks

    fabricated = [
        lid
        for lid, r in (graph.routes or {}).items()
        if (r or {}).get("geometry_source") == "fabricated"
    ]
    unmatched_opc = [
        e.id
        for e in graph.from_tos.values()
        if (e.connection_type or "").startswith("opc") and not e.matched
    ]
    spec = validate_spec_breaks(graph)
    clash = clash_check(graph) if graph.routes else {"hard_count": 0}
    flex = screen_graph(graph) if graph.routes else {}
    flex_pass = bool(flex) and all(s.get("status") == STATUS_PASS for s in flex.values())
    design_pressure_ok = bool(graph.pipelines) and all(
        (p.metadata or {}).get("DesignPressure") not in (None, "")
        or (p.metadata or {}).get("design_pressure") not in (None, "")
        for p in graph.pipelines.values()
    )
    return {
        "fabricated_count": len(fabricated),
        "unmatched_opc_count": len(unmatched_opc),
        "spec_break_violations": int(spec.get("violation_count") or 0),
        "clash_hard": int(clash.get("hard_count") or 0),
        "flex_screen_pass": flex_pass,
        "design_pressure_present": design_pressure_ok,
    }


def ladder_from_gates(gates: dict[str, Any]) -> str:
    """FEED → DD → IFC from the six B28 data gates."""
    ifc_ok = (
        int(gates.get("fabricated_count") or 0) == 0
        and int(gates.get("unmatched_opc_count") or 0) == 0
        and int(gates.get("spec_break_violations") or 0) == 0
        and int(gates.get("clash_hard") or 0) == 0
        and bool(gates.get("flex_screen_pass"))
        and bool(gates.get("design_pressure_present"))
    )
    if ifc_ok:
        return MaturityLevel.IFC.value
    if gates.get("design_pressure_present"):
        return MaturityLevel.DD.value
    return MaturityLevel.FEED.value


def issue_ifc(graph: TopologyGraph) -> dict[str, Any]:
    """Refuse IFC issue unless every B28 gate is green."""
    gates = ifc_issue_gates(graph)
    ladder = ladder_from_gates(gates)
    allowed = ladder == MaturityLevel.IFC.value
    failed = [k for k, ok in (
        ("fabricated_count", gates["fabricated_count"] == 0),
        ("unmatched_opc_count", gates["unmatched_opc_count"] == 0),
        ("spec_break_violations", gates["spec_break_violations"] == 0),
        ("clash_hard", gates["clash_hard"] == 0),
        ("flex_screen_pass", gates["flex_screen_pass"]),
        ("design_pressure_present", gates["design_pressure_present"]),
    ) if not ok]
    return {
        "allowed": allowed,
        "ladder": ladder,
        "reasons": gates,
        "failed": failed,
        "message": (
            f"IFC issue permitted at {ladder}"
            if allowed
            else f"Refused IFC issue: failed {failed} (ladder={ladder})"
        ),
    }


def assess_maturity(graph: TopologyGraph, job: Optional[JobPipeline] = None) -> dict[str, Any]:
    """Heuristic maturity assessment from graph completeness + stage status."""
    summary = graph.connectivity_summary()
    score_bits: list[str] = []
    level = MaturityLevel.FEED

    if summary["tag_count"] > 0 and summary["sheet_count"] > 0:
        level = MaturityLevel.L1
        score_bits.append("tags+sheets")
    if summary["pipeline_count"] > 0 and summary["from_to_count"] > 0:
        level = MaturityLevel.L2
        score_bits.append("topology")
    if summary["volume_count"] > 0 and summary["equipment_count"] > 0:
        level = MaturityLevel.L3_60
        score_bits.append("layout+equipment")
    if (
        summary["matched_joins"] > 0
        and summary["unmatched_joins"] == 0
        and summary["work_package_count"] > 0
    ):
        level = MaturityLevel.L4_90
        score_bits.append("joins+WPs")
    # IFC only if explicitly advanced + no unmatched + battery limits reviewed
    if (
        level == MaturityLevel.L4_90
        and summary["battery_limit_count"] > 0
        and summary["unmatched_tags"] == []
        and job is not None
        and all(s.status == StageStatus.DONE for s in job.stages)
        and job.target_maturity == MaturityLevel.IFC
    ):
        level = MaturityLevel.IFC
        score_bits.append("ifc-ready")

    if job is not None:
        job.current_maturity = level

    # Data-derived gate reasons (not sticky flags)
    gates = ifc_issue_gates(graph)
    reasons = {
        "fabricated_count": gates["fabricated_count"],
        "unmatched_opc_count": gates["unmatched_opc_count"],
        "spec_break_violations": gates["spec_break_violations"],
        "clash_hard": gates["clash_hard"],
        "flex_screen_pass": gates["flex_screen_pass"],
        "design_pressure_present": gates["design_pressure_present"],
        "factors": score_bits,
    }
    ladder = ladder_from_gates(gates)
    if gates["fabricated_count"]:
        level = min(level, MaturityLevel.L3_60, key=lambda x: MATURITY_ORDER.index(x))
        reasons["blocks_ifc"] = "fabricated_geometry"
    if ladder == MaturityLevel.IFC.value:
        level = MaturityLevel.IFC
    elif ladder == MaturityLevel.DD.value and maturity_index(level) < maturity_index(MaturityLevel.DD):
        level = MaturityLevel.DD
    return {
        "maturity": level.value,
        "level": level,
        "ladder": ladder,
        "factors": score_bits,
        "reasons": reasons,
        "gates": reasons,
        "summary": summary,
        "target": job.target_maturity.value if job else None,
    }


class MaturityGateError(PermissionError):
    """Raised when an export/action is refused due to insufficient maturity."""


def maturity_check(
    current: MaturityLevel,
    required: MaturityLevel = MaturityLevel.IFC,
    action: str = "export",
    graph: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Check whether current maturity allows an action.
    Refuses IFC-grade export if maturity < IFC.
    Refuses IFC/PCF export when any line has fabricated geometry.
    """
    allowed = meets_or_exceeds(current, required)
    result: dict[str, Any] = {
        "allowed": allowed,
        "current": current.value,
        "required": required.value,
        "action": action,
    }
    fabricated: list[str] = []
    if graph is not None:
        from threadforge.routing import ensure_routes, get_route

        ensure_routes(graph)
        for p in graph.pipelines.values():
            r = get_route(graph, p.id)
            if r.get("geometry_source") == "fabricated":
                fabricated.append(p.line_number)
    result["fabricated_lines"] = fabricated
    action_l = action.lower()
    if graph is not None and required == MaturityLevel.IFC and any(
        k in action_l for k in ("ifc", "issue", "export")
    ):
        issued = issue_ifc(graph)
        result["reasons"] = issued["reasons"]
        result["ladder"] = issued["ladder"]
        result["failed"] = issued["failed"]
        if not issued["allowed"]:
            result["allowed"] = False
            result["message"] = issued["message"]
            result["error"] = "MaturityGateError"
            return result
        result["allowed"] = True
        result["message"] = issued["message"]
        return result
    if fabricated and any(k in action_l for k in ("ifc", "pcf", "export")):
        allowed = False
        result["allowed"] = False
        result["message"] = (
            f"Refused {action}: fabricated geometry on lines {fabricated}"
        )
        result["error"] = "MaturityGateError"
        return result
    if not allowed:
        result["message"] = (
            f"Refused {action} as {required.value}-grade: "
            f"current maturity is {current.value} (< {required.value})"
        )
        result["error"] = "MaturityGateError"
    else:
        result["message"] = f"{action} permitted at {current.value}"
    return result


def assert_maturity(
    current: MaturityLevel,
    required: MaturityLevel = MaturityLevel.IFC,
    action: str = "export",
    graph: Optional[Any] = None,
) -> None:
    check = maturity_check(current, required, action, graph=graph)
    if not check["allowed"]:
        raise MaturityGateError(check["message"])


def crafted_ifc_ready_graph() -> TopologyGraph:
    """U-loop 6\" line at 38 °C with design pressure — all B28 gates green."""
    from threadforge.graph import TopologyGraph
    from threadforge.models import Equipment, Nozzle, Pipeline

    g = TopologyGraph()
    g.equipment["EQ-IFC-A"] = Equipment(id="EQ-IFC-A", tag="EQ-IFC-A", nozzles=["IFC-N1"])
    g.equipment["EQ-IFC-B"] = Equipment(id="EQ-IFC-B", tag="EQ-IFC-B", nozzles=["IFC-N2"])
    g.nozzles["IFC-N1"] = Nozzle(id="IFC-N1", tag="N1", equipment_id="EQ-IFC-A", x=0.0, y=0.0, z=5.0)
    g.nozzles["IFC-N2"] = Nozzle(id="IFC-N2", tag="N2", equipment_id="EQ-IFC-B", x=10.0, y=0.0, z=5.0)
    g.pipelines["LINE-IFC-OK"] = Pipeline(
        id="LINE-IFC-OK",
        line_number="IFC-OK",
        from_tag="IFC-N1",
        to_tag="IFC-N2",
        nominal_bore='6"',
        service="PROCESS",
        material="CS",
        metadata={"DesignPressure": 10.0, "design_temp_c": 38.0, "flange_class": 150},
    )
    # Developed L >> U so 319.4.1 passes (large slack).
    pts = [
        (0.0, 0.0, 5.0),
        (4.0, 0.0, 5.0),
        (4.0, 6.0, 5.0),
        (10.0, 6.0, 5.0),
        (10.0, 0.0, 5.0),
    ]
    length = 4.0 + 6.0 + 6.0 + 6.0
    g.routes["LINE-IFC-OK"] = {
        "line_id": "LINE-IFC-OK",
        "line_number": "IFC-OK",
        "nominal_bore": '6"',
        "points": [{"x": p[0], "y": p[1], "z": p[2]} for p in pts],
        "length_m": length,
        "geometry_source": "nozzle_xyz",
    }
    return g


def crafted_feed_graph() -> TopologyGraph:
    """Tags only — no design pressure → FEED, IFC refused."""
    from threadforge.graph import TopologyGraph
    from threadforge.models import Pipeline, Tag

    g = TopologyGraph()
    g.tags["T-FEED"] = Tag(id="T-FEED", name="T-FEED")
    g.pipelines["LINE-FEED"] = Pipeline(
        id="LINE-FEED",
        line_number="FEED",
        from_tag="T-FEED",
        to_tag="T-FEED",
        nominal_bore='4"',
    )
    return g


def mark_stage_done(job: JobPipeline, stage: JobStage, message: str = "Done") -> None:
    from datetime import datetime, timezone

    st = job.stage_state(stage)
    st.status = StageStatus.DONE
    st.message = message
    st.updated_at = datetime.now(timezone.utc)
