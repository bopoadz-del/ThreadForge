"""B24: constraint-based IWP release; look-ahead is released-only."""

from threadforge.iwp_release import IWP_RELEASE_PIN, apply_iwp_release, crafted_release_graph
from threadforge.schedule_4d import Schedule4D


def test_release_ready_pin():
    g = crafted_release_graph()
    summary = apply_iwp_release(g)
    assert summary["released"] == IWP_RELEASE_PIN["released"]
    assert summary["blocked"] == IWP_RELEASE_PIN["blocked"]
    assert g.work_packages["IWP-REL-1"].metadata["release_ready"] is True
    assert g.work_packages["IWP-REL-2"].metadata["release_ready"] is False


def test_look_ahead_released_only():
    g = crafted_release_graph()
    apply_iwp_release(g)
    sch = Schedule4D(g)
    la = sch.look_ahead(weeks=3, from_date="2027-03-03", released_only=True)
    assert [w["id"] for w in la["work_packages"]] == ["IWP-REL-1"]
