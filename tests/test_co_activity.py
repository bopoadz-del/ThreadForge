"""Co-activity flags WPs overlapping in time AND same volume."""

from datetime import date

from threadforge.generators import build_work_packages
from threadforge.ingest_dexpi import load_fixture
from threadforge.schedule_4d import Schedule4D


def test_co_activity_flag(fixtures_dir):
    g = load_fixture()
    build_work_packages(g)
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    sched.attach_to_work_packages()

    result = sched.co_activity_check()
    assert result["flagged_count"] >= 1
    # VOL-A has PIP and EQP overlapping Feb/Mar 2027
    volumes = {f["volume_id"] for f in result["flagged"]}
    assert "VOL-A" in volumes or "VOL-B" in volumes
    for pair in result["flagged"]:
        assert pair["wp_a"] != pair["wp_b"]
        assert pair["volume_id"]


def test_no_flag_when_different_volumes():
    g = load_fixture()
    build_work_packages(g)
    # Force two WPs same time, different volumes — should not flag each other alone
    wp_a = g.work_packages.get("WP-VOL-A-PIP")
    wp_b = g.work_packages.get("WP-VOL-B-PIP")
    assert wp_a and wp_b
    wp_a.start = date(2027, 3, 1)
    wp_a.finish = date(2027, 3, 15)
    wp_b.start = date(2027, 3, 1)
    wp_b.finish = date(2027, 3, 15)
    # Clear other WP dates so only these two could interact
    for wp in g.work_packages.values():
        if wp.id not in (wp_a.id, wp_b.id):
            wp.start = None
            wp.finish = None
    sched = Schedule4D(g)
    result = sched.co_activity_check()
    assert result["flagged_count"] == 0
