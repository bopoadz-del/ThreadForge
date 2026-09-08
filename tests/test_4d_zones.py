"""B26: co-activity + crane/laydown zones pinned on sample_schedule.json."""

from pathlib import Path

from threadforge.generators import build_work_packages
from threadforge.ingest_dexpi import load_fixture
from threadforge.schedule_4d import SAMPLE_4D_PIN, Schedule4D


def test_sample_schedule_4d_pin(fixtures_dir: Path):
    g = load_fixture()
    build_work_packages(g)
    sch = Schedule4D(g)
    sch.load_json(fixtures_dir / "sample_schedule.json")
    sch.attach_to_work_packages()
    by = sch.conflicts_by_day()
    assert by["hard_count"] == SAMPLE_4D_PIN["hard_count"]
    assert by["soft_count"] == SAMPLE_4D_PIN["soft_count"]
    assert by["crane_count"] == SAMPLE_4D_PIN["crane_count"]
    assert by["laydown_count"] == SAMPLE_4D_PIN["laydown_count"]
    for day, row in SAMPLE_4D_PIN["days"].items():
        assert by["days"][day] == row
