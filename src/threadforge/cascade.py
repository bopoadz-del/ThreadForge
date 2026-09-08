"""Change → dirty artefacts cascade for the digital thread."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import (
    ArtefactDescriptor,
    ArtefactKind,
    ChangeEvent,
    DirtySet,
    JobPipeline,
    JobStage,
    StageStatus,
)

# Twelve artefact kinds in the digital-thread cascade (B27).
CASCADE_KINDS_12: list[ArtefactKind] = [
    ArtefactKind.ISOMETRIC,
    ArtefactKind.QUANTITIES,
    ArtefactKind.TEST_PACK,
    ArtefactKind.WORK_PACKAGE,
    ArtefactKind.PCF,
    ArtefactKind.DLB,
    ArtefactKind.GA,
    ArtefactKind.CSV,
    ArtefactKind.SYSTEM,
    ArtefactKind.SUPPORTS,
    ArtefactKind.ROUTES,
    ArtefactKind.CLASH,
]

# Downstream artefacts dirtied when a tag or line changes
TAG_DIRTY_KINDS = list(CASCADE_KINDS_12)

LINE_DIRTY_KINDS = list(CASCADE_KINDS_12)

STAGE_CASCADE: dict[JobStage, list[JobStage]] = {
    JobStage.UPLOAD: [JobStage.TOPOLOGY, JobStage.LAYOUT, JobStage.PIPING, JobStage.OUTPUTS],
    JobStage.TOPOLOGY: [JobStage.LAYOUT, JobStage.PIPING, JobStage.OUTPUTS],
    JobStage.LAYOUT: [JobStage.PIPING, JobStage.OUTPUTS],
    JobStage.PIPING: [JobStage.OUTPUTS],
    JobStage.OUTPUTS: [],
}


class CascadeEngine:
    """Tracks changes and computes dirty artefact sets; marks pipeline stages."""

    def __init__(self, graph: TopologyGraph, job: Optional[JobPipeline] = None) -> None:
        self.graph = graph
        self.job = job
        self.events: list[ChangeEvent] = []
        self.artefacts: dict[str, ArtefactDescriptor] = {}
        self.last_dirty: Optional[DirtySet] = None

    def register_artefact(self, art: ArtefactDescriptor) -> None:
        self.artefacts[art.id] = art

    def record_change(
        self,
        entity_type: str,
        entity_id: str,
        action: str = "revise",
        details: Optional[dict[str, Any]] = None,
    ) -> ChangeEvent:
        event = ChangeEvent(
            id=f"CHG-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=details or {},
        )
        self.events.append(event)
        dirty = self.compute_dirty(event)
        self.last_dirty = dirty
        self._apply_dirty(dirty)
        return event

    def compute_dirty(self, event: ChangeEvent) -> DirtySet:
        kinds: list[ArtefactKind]
        if event.entity_type in ("tag", "equipment", "instrument", "nozzle"):
            kinds = list(TAG_DIRTY_KINDS)
        elif event.entity_type in ("pipeline", "line"):
            kinds = list(LINE_DIRTY_KINDS)
        else:
            kinds = list(TAG_DIRTY_KINDS)

        artefact_ids: list[str] = []
        for art in self.artefacts.values():
            if art.kind not in kinds:
                continue
            scoped = bool(art.related_tags or art.related_lines)
            related = event.entity_id in art.related_tags or event.entity_id in art.related_lines
            if related or not scoped:
                artefact_ids.append(art.id)
        artefact_ids = sorted(artefact_ids)

        # WPs that contain the changed tag / line components
        affected_wps: list[str] = []
        for wp in self.graph.work_packages.values():
            if event.entity_id in wp.tags:
                affected_wps.append(wp.id)
            else:
                # line change: if any WP tag belongs to that line
                pipe = self.graph.pipelines.get(event.entity_id)
                if pipe:
                    line_tags = set(pipe.component_tags)
                    if pipe.from_tag:
                        line_tags.add(pipe.from_tag)
                    if pipe.to_tag:
                        line_tags.add(pipe.to_tag)
                    if line_tags.intersection(wp.tags):
                        affected_wps.append(wp.id)

        # Also dirty WPs by volume if tag has volume
        tag = self.graph.tags.get(event.entity_id)
        if tag and tag.volume_id:
            for wp in self.graph.work_packages.values():
                if wp.volume_id == tag.volume_id and wp.id not in affected_wps:
                    affected_wps.append(wp.id)

        affected_stages = [
            JobStage.PIPING,
            JobStage.OUTPUTS,
        ]
        if event.entity_type in ("tag", "equipment", "pipeline", "line"):
            affected_stages = [JobStage.TOPOLOGY, JobStage.PIPING, JobStage.OUTPUTS]

        return DirtySet(
            change_id=event.id,
            artefact_kinds=kinds,
            artefact_ids=artefact_ids,
            affected_wp_ids=affected_wps,
            affected_stages=affected_stages,
        )

    def _apply_dirty(self, dirty: DirtySet) -> None:
        # Shared geometry invalidated before any dependent regenerates.
        if ArtefactKind.ROUTES in dirty.artefact_kinds:
            self.graph.routes.clear()
        for aid in dirty.artefact_ids:
            if aid in self.artefacts:
                self.artefacts[aid].status = "dirty"
        for wid in dirty.affected_wp_ids:
            wp = self.graph.work_packages.get(wid)
            if wp:
                wp.status = "dirty"
        if self.job:
            for stage in dirty.affected_stages:
                st = self.job.stage_state(stage)
                if st.status == StageStatus.DONE:
                    st.status = StageStatus.DIRTY
                    st.updated_at = datetime.now(timezone.utc)
                    st.message = f"Dirtied by {dirty.change_id}"
            # Cascade further downstream
            for stage in list(dirty.affected_stages):
                for down in STAGE_CASCADE.get(stage, []):
                    st = self.job.stage_state(down)
                    if st.status == StageStatus.DONE:
                        st.status = StageStatus.DIRTY
                        st.updated_at = datetime.now(timezone.utc)

    def write_kind_file(
        self,
        kind: ArtefactKind,
        line_id: str,
        output_dir: Path,
    ) -> ArtefactDescriptor:
        """Write one artefact file for ``kind`` scoped to ``line_id`` (B27 hashes)."""
        from threadforge.clash import generate_clash_report
        from threadforge.generators import (
            build_systems_from_graph,
            build_test_packs,
            build_work_packages,
            generate_csv_export,
            generate_dlb,
            generate_ga,
            generate_isometric,
            generate_pcf,
            generate_quantities,
            generate_supports_stub,
            write_routes_artefact,
        )

        scoped = output_dir / line_id / kind.value
        scoped.mkdir(parents=True, exist_ok=True)
        if kind == ArtefactKind.PCF:
            art = generate_pcf(self.graph, line_id, scoped)
        elif kind == ArtefactKind.ISOMETRIC:
            art = generate_isometric(self.graph, line_id, scoped)
        elif kind == ArtefactKind.QUANTITIES:
            art = generate_quantities(self.graph, output_dir=scoped)
        elif kind == ArtefactKind.GA:
            art = generate_ga(self.graph, scoped)
        elif kind == ArtefactKind.DLB:
            art = generate_dlb(self.graph, scoped)
        elif kind == ArtefactKind.CSV:
            art = generate_csv_export(self.graph, scoped)
        elif kind == ArtefactKind.ROUTES:
            art = write_routes_artefact(self.graph, scoped)
        elif kind == ArtefactKind.SUPPORTS:
            art = generate_supports_stub(self.graph, scoped)
        elif kind == ArtefactKind.CLASH:
            art = generate_clash_report(self.graph, scoped)
        elif kind == ArtefactKind.TEST_PACK:
            packs = build_test_packs(self.graph)
            path = scoped / "test_packs.json"
            path.write_text(
                json.dumps([p.model_dump(mode="json") for p in packs], indent=2, sort_keys=True),
                encoding="utf-8",
            )
            art = ArtefactDescriptor(
                id=f"TPK-{line_id}",
                kind=kind,
                status="ready",
                path=str(path),
                related_lines=[line_id],
            )
        elif kind == ArtefactKind.WORK_PACKAGE:
            if not self.graph.work_packages:
                build_work_packages(self.graph)
            path = scoped / "work_packages.json"
            path.write_text(
                json.dumps(
                    [w.model_dump(mode="json") for w in self.graph.work_packages.values()],
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            art = ArtefactDescriptor(
                id=f"WP-{line_id}",
                kind=kind,
                status="ready",
                path=str(path),
                related_lines=[line_id],
            )
        elif kind == ArtefactKind.SYSTEM:
            arts = build_systems_from_graph(self.graph)
            path = scoped / "systems.json"
            path.write_text(
                json.dumps([a.payload for a in arts], indent=2, sort_keys=True),
                encoding="utf-8",
            )
            art = ArtefactDescriptor(
                id=f"SYS-{line_id}",
                kind=kind,
                status="ready",
                path=str(path),
                related_lines=[line_id],
            )
        else:
            raise ValueError(f"unsupported kind {kind}")
        art.related_lines = [line_id]
        art.id = f"{kind.value}-{line_id}"
        self.register_artefact(art)
        return art

    def dirty_summary(self) -> dict[str, Any]:
        if not self.last_dirty:
            return {"dirty": False}
        d = self.last_dirty
        return {
            "dirty": True,
            "change_id": d.change_id,
            "artefact_kinds": [k.value for k in d.artefact_kinds],
            "artefact_ids": list(d.artefact_ids),
            "affected_wp_ids": list(d.affected_wp_ids),
            "affected_stages": [s.value for s in d.affected_stages],
        }
