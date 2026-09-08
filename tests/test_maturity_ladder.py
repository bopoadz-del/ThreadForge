"""B28: FEED→DD→IFC from data; IFC refuses unless all gates pass."""

from threadforge.maturity import (
    crafted_feed_graph,
    crafted_ifc_ready_graph,
    issue_ifc,
    ladder_from_gates,
)


def test_ifc_ready_issues():
    r = issue_ifc(crafted_ifc_ready_graph())
    assert r["allowed"] is True
    assert r["ladder"] == "IFC"
    assert r["reasons"]["fabricated_count"] == 0
    assert r["reasons"]["flex_screen_pass"] is True


def test_feed_refuses_ifc():
    r = issue_ifc(crafted_feed_graph())
    assert r["allowed"] is False
    assert r["ladder"] == "FEED"
    assert "Refused" in r["message"]


def test_dd_when_pressure_but_flex_fails():
    assert (
        ladder_from_gates(
            {
                "fabricated_count": 0,
                "unmatched_opc_count": 0,
                "spec_break_violations": 0,
                "clash_hard": 0,
                "flex_screen_pass": False,
                "design_pressure_present": True,
            }
        )
        == "DD"
    )
