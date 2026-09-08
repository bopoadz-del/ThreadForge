"""Line / valve / instrument / tie-in lists as .xlsx (openpyxl).

Column contract: docs/exports.md
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Union

from threadforge.graph import TopologyGraph
from threadforge.models import ArtefactDescriptor, ArtefactKind

LINE_COLUMNS = [
    "line_id",
    "line_number",
    "from_tag",
    "to_tag",
    "nominal_bore",
    "service",
    "piping_class",
    "fluid_code",
    "insulation",
    "tracing",
    "sheet_id",
]
VALVE_COLUMNS = [
    "tag",
    "component_class",
    "line_id",
    "nominal_bore",
    "sheet_id",
]
INSTRUMENT_COLUMNS = [
    "tag",
    "instrument_type",
    "connected_to",
    "sheet_id",
    "loop_id",
]
TIEIN_COLUMNS = [
    "tag",
    "kind",
    "line_id",
    "sheet_id",
]


def _rewrite_xlsx_deterministic(path: Path) -> None:
    """Normalize zip member timestamps so MCP/HTTP export hashes match."""
    buf = io.BytesIO()
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name in sorted(zin.namelist()):
            info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, zin.read(name))
    path.write_bytes(buf.getvalue())


def _aid(prefix: str) -> str:
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _is_valve(cls: str) -> bool:
    return "VALVE" in (cls or "").upper()


def line_rows(graph: TopologyGraph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pipe in graph.pipelines.values():
        meta = pipe.metadata or {}
        ga = meta.get("generics") or {}
        rows.append(
            {
                "line_id": pipe.id,
                "line_number": pipe.line_number,
                "from_tag": pipe.from_tag or "",
                "to_tag": pipe.to_tag or "",
                "nominal_bore": pipe.nominal_bore or "",
                "service": pipe.service or "",
                "piping_class": meta.get("PipingClass") or ga.get("PipingClassCodeAssignmentClass") or "",
                "fluid_code": meta.get("FluidCode") or ga.get("FluidCodeAssignmentClass") or "",
                "insulation": meta.get("insulation_type") or meta.get("insulation") or "",
                "tracing": meta.get("tracing") or "",
                "sheet_id": pipe.sheet_id or "",
            }
        )
    return rows


def valve_rows(graph: TopologyGraph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in graph.piping_components.values():
        cls = str(rec.get("component_class") or "")
        if not _is_valve(cls):
            continue
        rows.append(
            {
                "tag": rec.get("tag") or rec.get("id"),
                "component_class": cls,
                "line_id": rec.get("segment_id") or "",
                "nominal_bore": (rec.get("generics") or {}).get(
                    "NominalDiameterRepresentationAssignmentClass", ""
                ),
                "sheet_id": "",
            }
        )
    return rows


def instrument_rows(graph: TopologyGraph) -> list[dict[str, Any]]:
    loop_by_assoc: dict[str, str] = {}
    for lid, loop in graph.instrumentation_loops.items():
        loop_by_assoc[lid] = str(loop.get("number") or lid)
    rows: list[dict[str, Any]] = []
    for inst in graph.instruments.values():
        loop_id = ""
        tag = graph.tags.get(inst.id)
        assoc = ((tag.metadata or {}).get("generics") if tag else {}) or {}
        for key, num in loop_by_assoc.items():
            if key in str(assoc) or key in (inst.connected_to or ""):
                loop_id = num
                break
        rows.append(
            {
                "tag": inst.tag,
                "instrument_type": inst.instrument_type or "",
                "connected_to": inst.connected_to or "",
                "sheet_id": inst.sheet_id or "",
                "loop_id": loop_id,
            }
        )
    return rows


def tiein_rows(graph: TopologyGraph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tag in graph.tags.values():
        role = (tag.metadata or {}).get("role")
        cls = (tag.engineering.component_class or "") if tag.engineering else ""
        if role == "off_page_connector" or "OffPage" in cls:
            rows.append(
                {
                    "tag": tag.name,
                    "kind": "opc",
                    "line_id": (tag.metadata or {}).get("line_id") or "",
                    "sheet_id": tag.sheet_id or "",
                }
            )
    for bl in graph.battery_limits.values():
        rows.append(
            {
                "tag": bl.tag_id,
                "kind": "battery_limit",
                "line_id": "",
                "sheet_id": "",
            }
        )
    return rows


def list_row_counts(graph: TopologyGraph) -> dict[str, int]:
    return {
        "lines": len(line_rows(graph)),
        "valves": len(valve_rows(graph)),
        "instruments": len(instrument_rows(graph)),
        "tie_ins": len(tiein_rows(graph)),
    }


def export_lists_xlsx(
    graph: TopologyGraph,
    path: Union[str, Path],
) -> ArtefactDescriptor:
    """Write four-sheet workbook from the topology graph."""
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pip install openpyxl") from exc

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheets = {
        "lines": (LINE_COLUMNS, line_rows(graph)),
        "valves": (VALVE_COLUMNS, valve_rows(graph)),
        "instruments": (INSTRUMENT_COLUMNS, instrument_rows(graph)),
        "tie_ins": (TIEIN_COLUMNS, tiein_rows(graph)),
    }
    wb = Workbook()
    first = True
    for name, (cols, rows) in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        ws.append(list(cols))
        for row in rows:
            ws.append([row.get(c, "") for c in cols])
    from datetime import datetime, timezone

    wb.properties.creator = "ThreadForge"
    wb.properties.lastModifiedBy = "ThreadForge"
    wb.properties.created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wb.properties.modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wb.save(str(out))
    _rewrite_xlsx_deterministic(out)
    counts = {name: len(rows) for name, (_c, rows) in sheets.items()}
    return ArtefactDescriptor(
        id=_aid("XLSX"),
        kind=ArtefactKind.XLSX,
        status="ready",
        path=str(out),
        payload={"sheets": counts, "columns": {
            "lines": LINE_COLUMNS,
            "valves": VALVE_COLUMNS,
            "instruments": INSTRUMENT_COLUMNS,
            "tie_ins": TIEIN_COLUMNS,
        }},
        message=f"lists xlsx lines={counts['lines']} valves={counts['valves']} "
        f"instruments={counts['instruments']} tie_ins={counts['tie_ins']}",
    )
