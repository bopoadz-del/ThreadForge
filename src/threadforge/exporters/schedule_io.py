"""Primavera XER and MS Project MSPDI export of a look-ahead.

XER: ``%T TASK`` / ``%T TASKPRED`` records (tab-separated Primavera text).
MSPDI: Microsoft Project XML, validated against the vendored MSPDI XSD.
Both re-parse to a task count that must equal the exported IWP count.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring

MSPDI_NS = "http://schemas.microsoft.com/project"
MSPDI_XSD_REL = Path("fixtures/public/mspdi/mspdi.xsd")


def _public_mspdi_xsd() -> Path:
    return Path(__file__).resolve().parents[3] / MSPDI_XSD_REL


def _iso(d: Union[str, date, datetime]) -> str:
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def _xml_dt(d: Union[str, date, datetime]) -> str:
    day = _iso(d)
    return f"{day}T08:00:00"


def iwp_tasks(look_ahead: dict[str, Any]) -> list[dict[str, Any]]:
    """IWPs (or work packages tagged IWP) inside a look-ahead payload."""
    tasks: list[dict[str, Any]] = []
    for wp in look_ahead.get("work_packages") or []:
        wtype = str(wp.get("wp_type") or "")
        if wtype and wtype != "IWP":
            continue
        tasks.append(
            {
                "id": wp.get("id") or wp.get("iwp_id"),
                "name": wp.get("name") or wp.get("id"),
                "start": wp.get("start"),
                "finish": wp.get("finish"),
                "wp_id": wp.get("id"),
            }
        )
    if not tasks:
        for act in look_ahead.get("activities") or []:
            tasks.append(
                {
                    "id": act.get("id"),
                    "name": act.get("name") or act.get("id"),
                    "start": act.get("start"),
                    "finish": act.get("finish"),
                    "wp_id": act.get("wp_id"),
                }
            )
    return tasks


def export_xer(look_ahead: dict[str, Any], path: Union[str, Path]) -> Path:
    """Write a Primavera XER with TASK + TASKPRED tables."""
    tasks = iwp_tasks(look_ahead)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "ERMHDR\t18.8\t2026-09-08\tProject\tadmin\tPrimavera\t",
        "%T\tPROJECT",
        "%F\tproj_id\tproj_short_name\tproj_name",
        "%R\t1\tTF-LA\tThreadForge look-ahead",
        "%T\tTASK",
        "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\tstart_date\tend_date",
    ]
    for i, t in enumerate(tasks, start=1):
        lines.append(
            "\t".join(
                [
                    "%R",
                    str(i),
                    "1",
                    str(t["id"]),
                    str(t["name"]),
                    "TT_Task",
                    _iso(t.get("start") or look_ahead.get("from") or "2027-03-03"),
                    _iso(t.get("finish") or look_ahead.get("to") or "2027-03-24"),
                ]
            )
        )
    lines.append("%T\tTASKPRED")
    lines.append("%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type")
    pred_n = 0
    for i in range(2, len(tasks) + 1):
        pred_n += 1
        lines.append(f"%R\t{pred_n}\t{i}\t{i - 1}\tPR_FS")
    lines.append("%E")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def parse_xer(source: Union[str, Path]) -> dict[str, list[dict[str, str]]]:
    """Re-parse XER ``%T`` / ``%F`` / ``%R`` tables."""
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = str(source)
    tables: dict[str, list[dict[str, str]]] = {}
    current = ""
    fields: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        kind = parts[0].strip()
        if kind == "%T":
            current = parts[1].strip() if len(parts) > 1 else ""
            tables.setdefault(current, [])
            fields = []
        elif kind == "%F":
            fields = [p.strip() for p in parts[1:]]
        elif kind == "%R" and current:
            vals = [p.strip() for p in parts[1:]]
            tables[current].append(dict(zip(fields, vals)))
    return tables


def export_mspdi(look_ahead: dict[str, Any], path: Union[str, Path]) -> Path:
    """Write MSPDI XML (namespace ``http://schemas.microsoft.com/project``)."""
    tasks = iwp_tasks(look_ahead)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    project = Element("Project")
    project.set("xmlns", MSPDI_NS)
    SubElement(project, "SaveVersion").text = "14"
    SubElement(project, "Name").text = "ThreadForge look-ahead"
    SubElement(project, "Title").text = "TF-LA"
    tasks_el = SubElement(project, "Tasks")
    for i, t in enumerate(tasks, start=1):
        task = SubElement(tasks_el, "Task")
        SubElement(task, "UID").text = str(i)
        SubElement(task, "ID").text = str(i)
        SubElement(task, "Name").text = str(t["name"])
        SubElement(task, "Start").text = _xml_dt(t.get("start") or look_ahead.get("from") or "2027-03-03")
        SubElement(task, "Finish").text = _xml_dt(t.get("finish") or look_ahead.get("to") or "2027-03-24")
        SubElement(task, "OutlineLevel").text = "1"
        if i > 1:
            link = SubElement(task, "PredecessorLink")
            SubElement(link, "PredecessorUID").text = str(i - 1)
            SubElement(link, "Type").text = "1"
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(project, encoding="utf-8")
    out.write_bytes(xml)
    return out


def parse_mspdi(path: Union[str, Path]) -> dict[str, Any]:
    """Re-parse MSPDI and count Task elements."""
    root = fromstring(Path(path).read_bytes())
    ns = {"p": MSPDI_NS}
    tasks = root.findall(".//{http://schemas.microsoft.com/project}Task")
    if not tasks:
        tasks = root.findall(".//Task")
    names = []
    for t in tasks:
        name_el = t.find("{http://schemas.microsoft.com/project}Name")
        if name_el is None:
            name_el = t.find("Name")
        names.append(name_el.text if name_el is not None else "")
    return {"task_count": len(tasks), "names": names, "ns": ns}


def validate_mspdi(path: Union[str, Path], xsd_path: Optional[Path] = None) -> dict[str, Any]:
    """xmlschema validate against the vendored MSPDI XSD."""
    import xmlschema

    xsd = xsd_path or _public_mspdi_xsd()
    schema = xmlschema.XMLSchema(str(xsd))
    errors = list(schema.iter_errors(str(path)))
    return {
        "engine": "xmlschema",
        "xsd": str(xsd),
        "n_errors": len(errors),
        "ok": len(errors) == 0,
        "errors": [str(e) for e in errors[:5]],
    }
