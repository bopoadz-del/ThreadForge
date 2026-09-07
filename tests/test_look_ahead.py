"""Look-ahead window filters activities/WPs."""

from threadforge.generators import build_work_packages
from threadforge.ingest_dexpi import load_fixture
from threadforge.schedule_4d import Schedule4D


def test_look_ahead_window(fixtures_dir):
    g = load_fixture()
    build_work_packages(g)
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    sched.attach_to_work_packages()

    # schedule_date is 2027-03-03; 3 weeks → to 2027-03-24
    result = sched.look_ahead(weeks=3)
    assert result["from"] == "2027-03-03"
    assert result["to"] == "2027-03-24"
    assert result["activity_count"] >= 3
    # TEL activity starts Apr 1 — outside 3-week window from Mar 3
    ids = {a["id"] for a in result["activities"]}
    assert "ACT-TEL-01" not in ids
    assert "ACT-PIP-120-01" in ids or "ACT-EQP-120-01" in ids


def test_look_ahead_custom_start(fixtures_dir):
    g = load_fixture()
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    result = sched.look_ahead(weeks=2, from_date="2027-04-01")
    ids = {a["id"] for a in result["activities"]}
    assert "ACT-TEL-01" in ids
