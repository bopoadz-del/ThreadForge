"""Cascade dirties isos, quantities, test packs, WPs on revise."""

from threadforge.cascade import CascadeEngine
from threadforge.generators import (
    build_work_packages,
    generate_isometric,
    generate_quantities,
)
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import ArtefactKind, JobPipeline, JobStage, StageStatus


def test_revise_line_dirties_artefacts_and_wps():
    g = load_fixture()
    build_work_packages(g)
    job = JobPipeline(job_id="T1", name="test")
    for st in job.stages:
        st.status = StageStatus.DONE
    engine = CascadeEngine(g, job)

    qty = generate_quantities(g)
    engine.register_artefact(qty)
    iso = generate_isometric(g, "LINE-120-P-1001")
    engine.register_artefact(iso)

    g.revise_pipeline("LINE-120-P-1001", {"service": "PROCESS-REV"})
    event = engine.record_change("pipeline", "LINE-120-P-1001", "revise", {"service": "PROCESS-REV"})

    dirty = engine.last_dirty
    assert dirty is not None
    assert dirty.change_id == event.id
    assert ArtefactKind.ISOMETRIC in dirty.artefact_kinds
    assert ArtefactKind.QUANTITIES in dirty.artefact_kinds
    assert ArtefactKind.TEST_PACK in dirty.artefact_kinds
    assert ArtefactKind.WORK_PACKAGE in dirty.artefact_kinds
    assert iso.id in dirty.artefact_ids or qty.id in dirty.artefact_ids
    assert engine.artefacts[iso.id].status == "dirty" or engine.artefacts[qty.id].status == "dirty"
    # Downstream stages marked dirty
    assert job.stage_state(JobStage.OUTPUTS).status == StageStatus.DIRTY
    assert len(dirty.affected_wp_ids) >= 1


def test_revise_tag_dirties_wps_by_membership():
    g = load_fixture()
    build_work_packages(g)
    engine = CascadeEngine(g)
    g.revise_tag("120-VEPR-2010", {"engineering": {"equipment_description": "REV DRUM"}})
    engine.record_change("tag", "120-VEPR-2010", "revise")
    dirty = engine.last_dirty
    assert dirty is not None
    assert "WP-VOL-A-EQP" in dirty.affected_wp_ids or any(
        "VOL-A" in w for w in dirty.affected_wp_ids
    )
