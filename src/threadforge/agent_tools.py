"""Agent-callable tool functions for ThreadForge.

Each public function is a stable tool surface an agent can call.
Session state is held in module-level `_Session` for the MVP CLI/demo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from threadforge.cascade import CascadeEngine
from threadforge.clash import generate_clash_report
from threadforge.generators import (
    build_test_packs as _gen_build_test_packs,
)
from threadforge.generators import (
    build_work_packages as _gen_build_work_packages,
)
from threadforge.generators import (
    default_output_dir,
    export_all_piping_artefacts,
    generate_csv_export,
    generate_dlb,
    generate_ga,
    generate_isometric,
    generate_pcf,
    generate_quantities,
    generate_supports_stub,
    regenerate_dirty,
    write_routes_artefact,
)
from threadforge.graph import TopologyGraph
from threadforge.ingest_dexpi import (
    coverage_report,
    default_fixture_path,
    load_fixture,
    parse_dexpi_xml,
)
from threadforge.maturity import assess_maturity, mark_stage_done
from threadforge.maturity import maturity_check as _maturity_check
from threadforge.models import (
    JobPipeline,
    JobStage,
    MaturityLevel,
    StageStatus,
    WPType,
)
from threadforge.schedule_4d import Schedule4D


class _Session:
    def __init__(self) -> None:
        self.graph: Optional[TopologyGraph] = None
        self.job: Optional[JobPipeline] = None
        self.cascade: Optional[CascadeEngine] = None
        self.schedule: Optional[Schedule4D] = None
        self.test_packs: list[Any] = []
        self.output_dir: Path = default_output_dir()


SESSION = _Session()


def _require_graph() -> TopologyGraph:
    if SESSION.graph is None:
        raise RuntimeError("No graph loaded — call ingest_dexpi first")
    return SESSION.graph


def _ensure_job() -> JobPipeline:
    if SESSION.job is None:
        SESSION.job = JobPipeline(job_id="JOB-001", name="demo-job")
    if SESSION.cascade is None and SESSION.graph is not None:
        SESSION.cascade = CascadeEngine(SESSION.graph, SESSION.job)
    return SESSION.job


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def ingest_dexpi(path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Parse Proteus/DEXPI-shaped XML (or default fixture) into the topology graph."""
    if path is None:
        graph = load_fixture()
        source = str(default_fixture_path())
    else:
        p = Path(path)
        if p.name.endswith(".xml") and not p.is_absolute() and not p.exists():
            # allow fixture name
            try:
                graph = load_fixture(p.name)
                source = str(p)
            except FileNotFoundError:
                graph = parse_dexpi_xml(path)
                source = str(path)
        else:
            graph = parse_dexpi_xml(path)
            source = str(path)
    SESSION.graph = graph
    job = JobPipeline(
        job_id="JOB-001",
        name=graph.metadata.get("plant", "job"),
        sheet_count=len(graph.sheets),
        target_maturity=MaturityLevel.L4_90,
    )
    mark_stage_done(job, JobStage.UPLOAD, "XML ingested")
    mark_stage_done(job, JobStage.TOPOLOGY, "Tags/lines/from-to built")
    if graph.volumes:
        mark_stage_done(job, JobStage.LAYOUT, "Design volumes loaded")
    SESSION.job = job
    SESSION.cascade = CascadeEngine(graph, job)
    SESSION.schedule = Schedule4D(graph)
    assess_maturity(graph, job)
    return {
        "ok": True,
        "source": source,
        "summary": graph.connectivity_summary(),
        "maturity": job.current_maturity.value,
        "stages": {s.stage.value: s.status.value for s in job.stages},
        "multi_sheet": graph.metadata.get("multi_sheet"),
        "dexpi_gaps": coverage_report()["gaps"][:5],
    }


def query_graph(**filters: Any) -> dict[str, Any]:
    """Query tags, lines, neighbors, volumes, or full summary."""
    graph = _require_graph()
    return graph.query(**filters)


def revise_pid(
    entity_type: str,
    entity_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Revise a tag or pipeline; records change and marks dirty artefacts."""
    graph = _require_graph()
    job = _ensure_job()
    assert SESSION.cascade is not None

    if entity_type in ("tag", "equipment", "instrument"):
        revised = graph.revise_tag(entity_id, updates)
        payload = revised.model_dump(mode="json")
    elif entity_type in ("pipeline", "line"):
        revised_p = graph.revise_pipeline(entity_id, updates)
        payload = revised_p.model_dump(mode="json")
    else:
        raise ValueError(f"Unsupported entity_type: {entity_type}")

    event = SESSION.cascade.record_change(entity_type, entity_id, "revise", updates)
    return {
        "ok": True,
        "change_id": event.id,
        "entity": payload,
        "dirty": SESSION.cascade.dirty_summary(),
        "stages": {s.stage.value: s.status.value for s in job.stages},
    }


def cascade_rerun() -> dict[str, Any]:
    """Re-run generators for artefacts dirtied by the last change."""
    graph = _require_graph()
    if SESSION.cascade is None or SESSION.cascade.last_dirty is None:
        return {"ok": True, "message": "Nothing dirty", "regenerated": []}
    dirty = SESSION.cascade.last_dirty
    result = regenerate_dirty(
        graph, dirty.artefact_kinds, dirty.affected_wp_ids, output_dir=SESSION.output_dir
    )
    for art in SESSION.cascade.artefacts.values():
        if art.id in dirty.artefact_ids or art.kind in dirty.artefact_kinds:
            art.status = "ready" if art.status == "dirty" else art.status
    job = _ensure_job()
    for stage in dirty.affected_stages:
        st = job.stage_state(stage)
        if st.status == StageStatus.DIRTY:
            st.status = StageStatus.DONE
            st.message = "Re-run complete"
            st.updated_at = datetime.now(timezone.utc)
    for wid in dirty.affected_wp_ids:
        wp = graph.work_packages.get(wid)
        if wp and wp.status == "dirty":
            wp.status = "planned"
    return {"ok": True, "change_id": dirty.change_id, **result}


def build_test_packs_tool() -> dict[str, Any]:
    """Build test packs from system boundary tags."""
    graph = _require_graph()
    packs = _gen_build_test_packs(graph)
    SESSION.test_packs = packs
    return {
        "ok": True,
        "count": len(packs),
        "test_packs": [p.model_dump(mode="json") for p in packs],
    }


def build_work_packages_tool(wp_type: str = "CWP") -> dict[str, Any]:
    """Build CWP/IWP work packages from design volumes + tags."""
    graph = _require_graph()
    graph.work_packages.clear()
    wps = _gen_build_work_packages(graph, wp_type=WPType(wp_type))
    job = _ensure_job()
    if job.stage_state(JobStage.LAYOUT).status != StageStatus.DONE:
        mark_stage_done(job, JobStage.LAYOUT, "Volumes → WPs")
    return {
        "ok": True,
        "count": len(wps),
        "work_packages": [w.model_dump(mode="json") for w in wps],
    }


def attach_schedule(path: Union[str, Path]) -> dict[str, Any]:
    """Import schedule JSON/CSV and attach dates to work packages."""
    graph = _require_graph()
    if SESSION.schedule is None:
        SESSION.schedule = Schedule4D(graph)
    path = Path(path)
    if path.suffix.lower() == ".csv":
        n = SESSION.schedule.load_csv(path)
    else:
        n = SESSION.schedule.load_json(path)
    updated = SESSION.schedule.attach_to_work_packages()
    return {
        "ok": True,
        "activities_loaded": n,
        "wps_updated": updated,
        "schedule_date": SESSION.schedule.schedule_date.isoformat(),
    }


def look_ahead(
    weeks: int = 3,
    from_date: Optional[str] = None,
    disciplines: Optional[list[str]] = None,
    export_csv: bool = False,
) -> dict[str, Any]:
    """List WPs/activities in the look-ahead window (optional discipline filter + CSV)."""
    if SESSION.schedule is None:
        raise RuntimeError("No schedule — call attach_schedule first")
    result = SESSION.schedule.look_ahead(
        weeks=weeks, from_date=from_date, disciplines=disciplines
    )
    if export_csv:
        out = SESSION.output_dir / "schedule" / "look_ahead.csv"
        SESSION.schedule.export_look_ahead_csv(
            out, weeks=weeks, from_date=from_date, disciplines=disciplines
        )
        result["csv_path"] = str(out)
    return result


def co_activity_check(
    disciplines: Optional[list[str]] = None,
    export_report: bool = False,
) -> dict[str, Any]:
    """Flag work packages that overlap in time and share a design volume."""
    if SESSION.schedule is None:
        raise RuntimeError("No schedule — call attach_schedule first")
    result = SESSION.schedule.co_activity_check(disciplines=disciplines)
    if export_report:
        out = SESSION.output_dir / "schedule" / "co_activity_report.json"
        SESSION.schedule.export_co_activity_report(out, disciplines=disciplines)
        result["report_path"] = str(out)
    return result


def maturity_check(
    required: str = "IFC",
    action: str = "export",
) -> dict[str, Any]:
    """Refuse IFC-grade export when current maturity is below the gate."""
    graph = _require_graph()
    job = _ensure_job()
    assessment = assess_maturity(graph, job)
    check = _maturity_check(
        job.current_maturity,
        MaturityLevel(required),
        action=action,
    )
    return {**check, "assessment": assessment}


def export_artefacts(output_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Write PCF, ISO, GA, routes, quantities under output/."""
    graph = _require_graph()
    out = Path(output_dir) if output_dir else SESSION.output_dir
    SESSION.output_dir = out
    return {"ok": True, **export_all_piping_artefacts(graph, out)}


def clash_check(clearance: float = 0.025) -> dict[str, Any]:
    """Run capsule clash detection; write output/clash/clash_report.json."""
    graph = _require_graph()
    art = generate_clash_report(graph, output_dir=SESSION.output_dir)
    return {"ok": True, **art.model_dump(mode="json"), "clearance": clearance}


def dexpi_coverage() -> dict[str, Any]:
    """Report supported DEXPI-shaped elements vs known gaps (WALL)."""
    return coverage_report()


def run_pipeline_stage(stage: str, run_all: bool = False) -> dict[str, Any]:
    """Run one (or all) Pid-to-3d pipeline stages."""
    graph = _require_graph()
    job = _ensure_job()
    assert SESSION.cascade is not None
    out = SESSION.output_dir

    order = list(JobStage)
    if run_all:
        stages = order
    else:
        stages = [JobStage(stage)]

    results: list[dict[str, Any]] = []
    for stg in stages:
        st = job.stage_state(stg)
        st.status = StageStatus.RUNNING
        st.updated_at = datetime.now(timezone.utc)
        artefacts: list[dict[str, Any]] = []

        if stg == JobStage.UPLOAD:
            st.message = "Upload already satisfied by ingest"
        elif stg == JobStage.TOPOLOGY:
            st.message = f"Topology: {graph.connectivity_summary()}"
        elif stg == JobStage.LAYOUT:
            if not graph.volumes:
                st.message = "No design volumes — layout partial"
            else:
                st.message = f"{len(graph.volumes)} design volumes"
            if not graph.work_packages:
                _gen_build_work_packages(graph)
        elif stg == JobStage.PIPING:
            art = write_routes_artefact(graph, out)
            SESSION.cascade.register_artefact(art)
            artefacts.append(art.model_dump(mode="json"))
            art2 = generate_supports_stub(graph, out)
            SESSION.cascade.register_artefact(art2)
            artefacts.append(art2.model_dump(mode="json"))
            for lid in list(graph.pipelines.keys())[:3]:
                iso = generate_isometric(graph, lid, out)
                SESSION.cascade.register_artefact(iso)
                artefacts.append(iso.model_dump(mode="json"))
            st.message = "Piping routes + iso packages generated"
        elif stg == JobStage.OUTPUTS:
            factories: list[Any] = [
                lambda: generate_quantities(graph, output_dir=out),
                lambda: generate_csv_export(graph, out),
                lambda: generate_ga(graph, out),
                lambda: generate_dlb(graph, out),
            ]
            for factory in factories:
                art = factory()
                SESSION.cascade.register_artefact(art)
                artefacts.append(art.model_dump(mode="json"))
            for lid in list(graph.pipelines.keys())[:2]:
                pcf = generate_pcf(graph, lid, out)
                SESSION.cascade.register_artefact(pcf)
                artefacts.append(pcf.model_dump(mode="json"))
            st.message = "Output artefacts written (PCF/GA/CSV/QTY)"

        mark_stage_done(job, stg, st.message or "Done")
        results.append(
            {
                "stage": stg.value,
                "status": st.status.value,
                "message": st.message,
                "artefacts": artefacts,
            }
        )

    assessment = assess_maturity(graph, job)
    return {
        "ok": True,
        "results": results,
        "maturity": assessment,
        "stages": {s.stage.value: s.status.value for s in job.stages},
        "output_dir": str(out),
    }


# Public names matching the deliverable tool list
build_test_packs = build_test_packs_tool
build_work_packages = build_work_packages_tool


TOOL_REGISTRY: dict[str, Any] = {
    "ingest_dexpi": ingest_dexpi,
    "query_graph": query_graph,
    "revise_pid": revise_pid,
    "cascade_rerun": cascade_rerun,
    "build_test_packs": build_test_packs_tool,
    "build_work_packages": build_work_packages_tool,
    "attach_schedule": attach_schedule,
    "look_ahead": look_ahead,
    "co_activity_check": co_activity_check,
    "maturity_check": maturity_check,
    "run_pipeline_stage": run_pipeline_stage,
    "export_artefacts": export_artefacts,
    "dexpi_coverage": dexpi_coverage,
    "clash_check": clash_check,
}


def list_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())


def call_tool(name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
    """Dispatch a tool by name (used by agent REPL)."""
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}. Available: {list_tools()}")
    fn = TOOL_REGISTRY[name]
    return fn(**(arguments or {}))
