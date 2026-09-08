"""B18 — render iso sheets and GA to PDF (reportlab).

Page count equals sheet count. Text is extractable via pypdf and includes the
line number plus HEURISTIC — NOT FOR CONSTRUCTION.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import ArtefactDescriptor, ArtefactKind


def _aid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


NFC = "HEURISTIC — NOT FOR CONSTRUCTION"


def _require_reportlab() -> Any:
    try:
        from reportlab.lib.pagesizes import A3
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover
        raise ImportError("reportlab is required for PDF export — pip install reportlab") from exc
    return canvas, A3


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


def _draw_header(c: Any, width: float, height: float, title: str, line_number: str, extra: str = "") -> None:
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, height - 40, title)
    c.setFont("Helvetica", 12)
    c.drawString(36, height - 58, f"Line {line_number}")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0.75, 0.15, 0.1)
    c.drawString(36, height - 76, NFC)
    c.setFillColorRGB(0, 0, 0)
    if extra:
        c.setFont("Helvetica", 10)
        c.drawString(36, height - 94, extra)


def export_iso_pdf(
    graph: TopologyGraph,
    line_id: str,
    output_path: Optional[Path] = None,
) -> ArtefactDescriptor:
    from threadforge.generators import generate_isometric

    canvas_mod, a3 = _require_reportlab()
    art = generate_isometric(graph, line_id)
    payload = art.payload or {}
    sheets = list(payload.get("sheets") or [])
    line_number = str(payload.get("line_number") or line_id)
    if output_path is None:
        output_path = Path("output/pdf") / f"{line_number.replace('/', '_')}.iso.pdf"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas_mod.Canvas(str(output_path), pagesize=a3)
    width, height = a3
    if not sheets:
        sheets = [{"sheet": 1, "n_of": 1, "spool_id": "", "length_m": 0.0, "dim_sum_mm": 0, "bom": []}]
    for sh in sheets:
        n = int(sh.get("sheet") or 1)
        n_of = int(sh.get("n_of") or len(sheets))
        spool = str(sh.get("spool_id") or "")
        extra = (
            f"sheet {n}/{n_of}  spool {spool}  "
            f"L={float(sh.get('length_m') or 0):.3f} m  dim_sum_mm={sh.get('dim_sum_mm')}"
        )
        _draw_header(c, width, height, f"ISO {line_number}", line_number, extra)
        c.setFont("Helvetica", 10)
        y = height - 120
        c.drawString(36, y, f"BOM sheet {n}:")
        y -= 16
        for item in sh.get("bom") or []:
            c.drawString(48, y, f"{item.get('tag')} {item.get('type')} {item.get('length_m')}")
            y -= 14
        cuts = sh.get("cut_lengths_m") or []
        c.drawString(36, y - 8, "cut_lengths_m=" + " ".join(f"{v:.3f}" for v in cuts))
        c.drawString(36, 40, NFC)
        c.showPage()
    c.save()
    text = extract_pdf_text(output_path)
    pages = pdf_page_count(output_path)
    return ArtefactDescriptor(
        id=_aid("PDF"),
        kind=ArtefactKind.PDF,
        status="ready",
        path=str(output_path),
        related_lines=[line_id],
        payload={
            "kind": "iso",
            "line_number": line_number,
            "page_count": pages,
            "sheet_count": len(sheets),
            "text_has_line": line_number in text,
            "text_has_nfc": NFC in text,
        },
        message=f"iso PDF {pages} pages",
    )


def export_ga_pdf(
    graph: TopologyGraph,
    output_path: Optional[Path] = None,
) -> ArtefactDescriptor:
    from threadforge.generators import write_ga_svg

    canvas_mod, a3 = _require_reportlab()
    if output_path is None:
        output_path = Path("output/pdf/plot_plan.pdf")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [p.line_number for p in graph.pipelines.values()]
    title_line = lines[0] if lines else "PLANT"
    c = canvas_mod.Canvas(str(output_path), pagesize=a3)
    width, height = a3
    _draw_header(c, width, height, "GA / Plot Plan", title_line, f"lines={', '.join(lines)}")
    c.setFont("Helvetica", 10)
    y = height - 120
    for lid, pipe in graph.pipelines.items():
        c.drawString(36, y, f"{pipe.line_number}  {pipe.nominal_bore}  {pipe.from_tag}→{pipe.to_tag}")
        y -= 14
    svg = write_ga_svg(graph)
    c.setFont("Helvetica", 8)
    c.drawString(36, 56, f"GA svg_bytes={len(svg.encode('utf-8'))}")
    c.drawString(36, 40, NFC)
    c.showPage()
    c.save()
    text = extract_pdf_text(output_path)
    pages = pdf_page_count(output_path)
    return ArtefactDescriptor(
        id=_aid("PDF"),
        kind=ArtefactKind.PDF,
        status="ready",
        path=str(output_path),
        payload={
            "kind": "ga",
            "line_number": title_line,
            "page_count": pages,
            "sheet_count": 1,
            "text_has_line": title_line in text,
            "text_has_nfc": NFC in text,
            "line_numbers": lines,
        },
        message=f"GA PDF {pages} pages",
    )
