"""Look-ahead discipline filters + CSV / co-activity report export."""


from threadforge.generators import build_work_packages
from threadforge.ingest_dexpi import load_fixture
from threadforge.schedule_4d import Schedule4D


def test_discipline_filter_pip_only(fixtures_dir):
    g = load_fixture()
    build_work_packages(g)
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    result = sched.look_ahead(weeks=6, disciplines=["PIP"])
    assert result["disciplines_filter"] == ["PIP"]
    for a in result["activities"]:
        assert a["discipline"] == "PIP"
    # TEL/ELE excluded
    ids = {a["id"] for a in result["activities"]}
    assert "ACT-TEL-01" not in ids
    assert "ACT-ELE-01" not in ids
    assert any(i.startswith("ACT-PIP") for i in ids)


def test_look_ahead_csv_export(fixtures_dir, tmp_path):
    g = load_fixture()
    build_work_packages(g)
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    out = tmp_path / "look_ahead.csv"
    path = sched.export_look_ahead_csv(
        out, weeks=3, disciplines=["PIP", "INS", "ELE", "TEL"]
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "id,name,wp_id,discipline" in text
    assert "ACT-" in text


def test_co_activity_report_has_volumes(fixtures_dir, tmp_path):
    g = load_fixture()
    build_work_packages(g)
    sched = Schedule4D(g)
    sched.load_json(fixtures_dir / "sample_schedule.json")
    sched.attach_to_work_packages()
    report_path = sched.export_co_activity_report(tmp_path / "co.json")
    import json

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["flagged_count"] >= 1
    assert "volumes_involved" in data
    assert data["flagged"][0]["volume"]["id"]
