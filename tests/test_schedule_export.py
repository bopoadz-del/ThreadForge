"""B25: Primavera XER + MSPDI reparse; task count = IWP count."""

from threadforge.exporters.schedule_io import (
    export_mspdi,
    export_xer,
    parse_mspdi,
    parse_xer,
    validate_mspdi,
)
from threadforge.iwp_release import apply_iwp_release, crafted_release_graph
from threadforge.schedule_4d import Schedule4D


def test_xer_and_mspdi_task_count(tmp_path):
    g = crafted_release_graph()
    apply_iwp_release(g)
    sch = Schedule4D(g)
    la = sch.look_ahead(weeks=3, from_date="2027-03-03", released_only=False)
    n = sum(1 for w in la["work_packages"] if w.get("wp_type") == "IWP")
    assert n == 5
    xer_p = tmp_path / "la.xer"
    xml_p = tmp_path / "la.xml"
    export_xer(la, xer_p)
    export_mspdi(la, xml_p)
    xer = parse_xer(xer_p)
    assert len(xer["TASK"]) == n
    assert "TASKPRED" in xer
    text = xer_p.read_text(encoding="utf-8")
    assert "%T\tTASK" in text
    assert "%T\tTASKPRED" in text
    msp = parse_mspdi(xml_p)
    assert msp["task_count"] == n
    val = validate_mspdi(xml_p)
    assert val["engine"] == "xmlschema"
    assert val["n_errors"] == 0
