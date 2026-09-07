"""D8: IWP/CWA depth + co-activity adjacent/craft density."""

from __future__ import annotations

from threadforge.generators import build_iwps, build_work_packages
from threadforge.ingest_dexpi import load_fixture
from threadforge.models import WPType
from threadforge.schedule_4d import Schedule4D, volumes_adjacent


def test_build_iwps_from_cwp():
    g = load_fixture()
    build_work_packages(g)
    iwps = build_iwps(g)
    assert iwps
    assert all(w.wp_type == WPType.IWP for w in iwps)
    assert all(w.id.startswith("IWP-") for w in iwps)
    assert all("cwa" in (w.metadata or {}) for w in iwps)
    assert all("weight_kg" in (w.metadata or {}) for w in iwps)


def test_volumes_adjacent():
    g = load_fixture()
    a, b = g.volumes["VOL-A"], g.volumes["VOL-B"]
    assert volumes_adjacent(a, b, gap_m=2.0)  # they touch at x=40


def test_co_activity_soft_adjacent_keys(graph_with_wps, fixtures_dir):
    sch = Schedule4D(graph=graph_with_wps)
    sch.load_json(fixtures_dir / "sample_schedule.json")
    report = sch.co_activity_check()
    assert "soft_adjacent" in report
    assert "craft_warnings" in report
