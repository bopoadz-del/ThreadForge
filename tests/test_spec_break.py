"""B23: spec-break validation; 150# into 300# is a violation."""

from threadforge.spec_break import crafted_150_into_300, validate_spec_breaks


def test_crafted_150_into_300_violation():
    report = validate_spec_breaks(crafted_150_into_300())
    assert report["violation_count"] >= 1
    assert any(
        v.get("kind") == "spec_break_violation"
        and any("150" in r and "300" in r for r in v.get("reasons") or [])
        for v in report["spec_break_violations"]
    )
