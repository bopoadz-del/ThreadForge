"""B20 — weld map + NDT schedule from B16 welds.

ASME B31.3 paragraph 341.4.1 Normal Fluid Service:
- (a) visual examination of all fabrication (VT 100 %).
- (b)(1) not less than 5 % of circumferential butt and miter groove welds
  by random radiography or ultrasonic examination.

NDT% default = 5 % RT. Number selected = ceil(0.05 × n_circumferential_BW)
so the examined fraction is never below 5 %. Counts reconcile to B16 weld_count.
"""

from __future__ import annotations

import csv
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import ArtefactDescriptor, ArtefactKind
from threadforge.tables import B31_3_341_4_1_CITE, B31_3_341_4_1_NORMAL_RT_PCT

WELD_CSV_COLUMNS = [
    "weld_id",
    "line_id",
    "line_number",
    "spool_id",
    "shop_field",
    "weld_type",
    "nominal_bore",
    "wall_mm",
    "vt_pct",
    "rt_pct",
    "rt_selected",
    "citation",
]


def _aid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def n_rt_required(n_circ_bw: int, pct: float = B31_3_341_4_1_NORMAL_RT_PCT) -> int:
    """ceil(pct/100 × n) — B31.3 341.4.1(b)(1) 'not less than 5%'."""
    if n_circ_bw <= 0:
        return 0
    return max(1, math.ceil(n_circ_bw * (pct / 100.0)))


def build_weld_map(graph: TopologyGraph) -> dict[str, Any]:
    from threadforge.generators import get_spool_report, write_pcf_text

    rows: list[dict[str, Any]] = []
    b16_weld_count = 0
    for lid in graph.pipelines:
        if "spools" not in (graph.routes.get(lid) or {}):
            write_pcf_text(graph, lid)
        rep = get_spool_report(graph, lid)
        welds = list(rep.get("welds") or [])
        b16_weld_count += int(rep.get("weld_count") or len(welds))
        n_bw = sum(1 for w in welds if w.get("weld_type") == "BW")
        n_rt = n_rt_required(n_bw)
        # Deterministic selection: field welds first, then shop, in weld_id order.
        ordered = sorted(
            welds,
            key=lambda w: (0 if w.get("shop_field") == "field" else 1, str(w.get("weld_id"))),
        )
        selected = {str(w["weld_id"]) for w in ordered[:n_rt]}
        for w in welds:
            wid = str(w.get("weld_id"))
            rows.append(
                {
                    "weld_id": wid,
                    "line_id": w.get("line_id") or lid,
                    "line_number": w.get("line_number"),
                    "spool_id": w.get("spool_id"),
                    "shop_field": w.get("shop_field"),
                    "weld_type": w.get("weld_type") or "BW",
                    "nominal_bore": w.get("nominal_bore"),
                    "wall_mm": w.get("wall_mm"),
                    "vt_pct": 100.0,
                    "rt_pct": B31_3_341_4_1_NORMAL_RT_PCT,
                    "rt_selected": wid in selected,
                    "citation": B31_3_341_4_1_CITE,
                }
            )
    n_sel = sum(1 for r in rows if r["rt_selected"])
    return {
        "rows": rows,
        "weld_count": len(rows),
        "b16_weld_count": b16_weld_count,
        "rt_selected": n_sel,
        "rt_pct": B31_3_341_4_1_NORMAL_RT_PCT,
        "citation": B31_3_341_4_1_CITE,
        "reconcile": len(rows) == b16_weld_count,
    }


def write_weld_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WELD_CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_weld_xlsx(rows: list[dict[str, Any]], path: Path) -> None:
    from openpyxl import Workbook

    from threadforge.exporters.xlsx import _rewrite_xlsx_deterministic

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "weld_ndt"
    ws.append(list(WELD_CSV_COLUMNS))
    for row in rows:
        ws.append([row.get(c, "") for c in WELD_CSV_COLUMNS])
    wb.properties.creator = "ThreadForge"
    wb.properties.lastModifiedBy = "ThreadForge"
    wb.properties.created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wb.properties.modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wb.save(str(path))
    _rewrite_xlsx_deterministic(path)


def export_weld_ndt(
    graph: TopologyGraph,
    output_dir: Optional[Path] = None,
) -> ArtefactDescriptor:
    payload = build_weld_map(graph)
    paths: dict[str, str] = {}
    if output_dir is not None:
        d = Path(output_dir) / "weld"
        csv_p = d / "weld_ndt.csv"
        xlsx_p = d / "weld_ndt.xlsx"
        write_weld_csv(payload["rows"], csv_p)
        write_weld_xlsx(payload["rows"], xlsx_p)
        paths = {"csv": str(csv_p), "xlsx": str(xlsx_p)}
        payload["files"] = paths
    return ArtefactDescriptor(
        id=_aid("WELD"),
        kind=ArtefactKind.CSV,
        status="ready",
        path=paths.get("csv"),
        payload=payload,
        message=f"weld map n={payload['weld_count']} rt={payload['rt_selected']}",
    )
