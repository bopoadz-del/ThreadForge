"""Maturity blocks IFC export when below gate."""

from threadforge.maturity import MaturityGateError, assert_maturity, maturity_check
from threadforge.models import MaturityLevel


def test_maturity_blocks_ifc_export():
    check = maturity_check(MaturityLevel.L4_90, MaturityLevel.IFC, action="export")
    assert check["allowed"] is False
    assert "Refused" in check["message"]
    assert check["current"] == "L4_90"
    assert check["required"] == "IFC"


def test_maturity_allows_when_ifc():
    check = maturity_check(MaturityLevel.IFC, MaturityLevel.IFC, action="export")
    assert check["allowed"] is True


def test_assert_raises():
    try:
        assert_maturity(MaturityLevel.L2, MaturityLevel.IFC)
        assert False, "expected MaturityGateError"
    except MaturityGateError as exc:
        assert "Refused" in str(exc)


def test_agent_tool_maturity_blocks():
    from threadforge import agent_tools

    agent_tools.ingest_dexpi()
    result = agent_tools.maturity_check(required="IFC", action="export")
    assert result["allowed"] is False
