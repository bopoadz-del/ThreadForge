"""B17 — one isometric sheet per shop spool.

Each sheet carries n/N, spool tag, weld symbols, cut lengths, and a per-sheet
BOM. Dimension sum on the sheet equals that spool's developed length (mm).
Not a certified ISOGEN drawing — title block is HEURISTIC — NOT FOR CONSTRUCTION.
"""

from __future__ import annotations

import math
from typing import Any, Optional


def _project(pt: dict[str, Any] | tuple[float, float, float]) -> tuple[float, float]:
    if isinstance(pt, dict):
        x, y, z = float(pt["x"]), float(pt["y"]), float(pt["z"])
    else:
        x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
    return (
        (x - y) * math.cos(math.radians(30)),
        (x + y) * math.sin(math.radians(30)) + z,
    )


def sheet_iso_svg(
    spool: dict[str, Any],
    *,
    line_number: str,
    sheet_n: int,
    sheet_n_of: int,
    welds: Optional[list[dict[str, Any]]] = None,
    bom: Optional[list[dict[str, Any]]] = None,
) -> str:
    """True 30° iso SVG for one spool. dim_sum_mm == round(spool.length_m * 1000)."""
    axis = list(spool.get("axis_points") or [])
    if len(axis) < 2:
        pts = list(spool.get("points") or [])
        axis = pts
    if len(axis) < 2:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
            f'<text x="20" y="40">ISO {line_number} sheet {sheet_n}/{sheet_n_of} empty</text></svg>'
        )

    proj = [_project(p) for p in axis]
    xs = [p[0] for p in proj]
    ys = [p[1] for p in proj]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    pad = 60
    w, h = 900, 640
    span_x = max(maxx - minx, 1e-3)
    span_y = max(maxy - miny, 1e-3)

    def sx(x: float) -> float:
        return pad + (x - minx) / span_x * (w - 2 * pad - 200)

    def sy(y: float) -> float:
        return h - pad - 80 - (y - miny) / span_y * (h - 2 * pad - 100)

    spool_id = str(spool.get("spool_id") or "")
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#0f1419"/>',
        f'<text x="{pad}" y="28" fill="#9ad1ff" font-family="monospace" font-size="16">'
        f"ISO {line_number}  spool {spool_id}  sheet {sheet_n}/{sheet_n_of}</text>",
        f'<text x="{pad}" y="48" fill="#fbbf24" font-family="monospace" font-size="11">'
        f"HEURISTIC — NOT FOR CONSTRUCTION</text>",
    ]
    parts.append(
        f'<g transform="translate({w - 80},{70})">'
        f'<line x1="0" y1="20" x2="0" y2="-20" stroke="#e2e8f0" stroke-width="2"/>'
        f'<polygon points="0,-28 -6,-12 6,-12" fill="#e2e8f0"/>'
        f'<text x="8" y="-18" fill="#e2e8f0" font-size="12" font-family="monospace">N north</text></g><!-- north-arrow -->'
    )
    # Official sheet total = spool developed length (PIPE chords + ELBOW B16.9 arcs).
    dim_sum_mm = int(round(float(spool.get("length_m") or 0.0) * 1000))
    d = " ".join(f"{'M' if i == 0 else 'L'} {sx(pt[0]):.1f} {sy(pt[1]):.1f}" for i, pt in enumerate(proj))
    parts.append(f'<path d="{d}" fill="none" stroke="#5eead4" stroke-width="3"/>')
    for i in range(len(axis) - 1):
        a, b = axis[i], axis[i + 1]
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        leng_m = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
        leng_mm = int(round(leng_m * 1000))
        mid = _project(((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2))
        parts.append(
            f'<text x="{sx(mid[0]):.1f}" y="{sy(mid[1]) - 8:.1f}" fill="#fca5a5" '
            f'font-family="monospace" font-size="10" text-anchor="middle">{leng_mm}</text>'
        )
    for pt in proj:
        parts.append(f'<circle cx="{sx(pt[0]):.1f}" cy="{sy(pt[1]):.1f}" r="4" fill="#fbbf24"/>')

    for wld in welds or []:
        xyz = wld.get("xyz")
        if not xyz:
            continue
        pr = _project((float(xyz[0]), float(xyz[1]), float(xyz[2])))
        cx, cy = sx(pr[0]), sy(pr[1])
        if wld.get("shop_field") == "field":
            # field weld: X (ISO 2553-style field flag)
            parts.append(
                f'<g class="weld-field" data-weld="{wld.get("weld_id")}"/>'
                f'<line x1="{cx - 6:.1f}" y1="{cy - 6:.1f}" x2="{cx + 6:.1f}" y2="{cy + 6:.1f}" '
                f'stroke="#fb7185" stroke-width="2"/>'
                f'<line x1="{cx - 6:.1f}" y1="{cy + 6:.1f}" x2="{cx + 6:.1f}" y2="{cy - 6:.1f}" '
                f'stroke="#fb7185" stroke-width="2"/>'
            )
        else:
            parts.append(
                f'<circle class="weld-shop" data-weld="{wld.get("weld_id")}" '
                f'cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="none" stroke="#38bdf8" stroke-width="2"/>'
            )
        parts.append(
            f'<text x="{cx + 8:.1f}" y="{cy - 6:.1f}" fill="#e2e8f0" font-family="monospace" '
            f'font-size="9">{wld.get("weld_id")}</text>'
        )

    cuts = spool.get("cut_lengths_m") or []
    cut_txt = " ".join(f"{c * 1000:.0f}" for c in cuts)
    parts.append(
        f'<text x="{pad}" y="68" fill="#86efac" font-family="monospace" font-size="11">'
        f"cut_lengths_mm={cut_txt or 'none'}</text>"
    )

    bom_list = bom or []
    bx0, by0 = w - 190, 100
    parts.append(
        f'<rect x="{bx0 - 10}" y="{by0 - 20}" width="180" height="{30 + 14 * max(len(bom_list), 1)}" '
        f'fill="#1e293b" stroke="#475569"/>'
    )
    parts.append(
        f'<text x="{bx0}" y="{by0}" fill="#e2e8f0" font-family="monospace" font-size="11">BOM sheet {sheet_n}</text>'
    )
    for i, item in enumerate(bom_list[:12]):
        parts.append(
            f'<text x="{bx0}" y="{by0 + 16 + i * 14}" fill="#94a3b8" font-family="monospace" font-size="10">'
            f'{str(item.get("tag", "?"))[:18]} {str(item.get("type", ""))[:8]}</text>'
        )
    parts.append(
        f'<rect x="{pad}" y="{h - 70}" width="{w - 2 * pad}" height="55" fill="#1e293b" stroke="#334155"/>'
    )
    parts.append(
        f'<text x="{pad + 8}" y="{h - 45}" fill="#e2e8f0" font-family="monospace" font-size="11">'
        f"Line {line_number} | spool {spool_id} | sheet {sheet_n}/{sheet_n_of} | "
        f"L={float(spool.get('length_m') or 0):.3f} m | dim_sum_mm={dim_sum_mm}</text>"
    )
    parts.append(
        f'<text x="{pad + 8}" y="{h - 25}" fill="#64748b" font-family="monospace" font-size="10">'
        f"HEURISTIC — NOT FOR CONSTRUCTION</text>"
    )
    parts.append(f"<!-- dim_sum_mm={dim_sum_mm} -->")
    parts.append("</svg>")
    return "\n".join(parts)


def spool_bom(spool: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, cut in enumerate(spool.get("cut_lengths_m") or [], start=1):
        rows.append({"tag": f"PIPE-{i}", "type": "PIPE", "length_m": cut})
    for fit in spool.get("fittings") or []:
        rows.append({"tag": fit.get("tag") or fit.get("kind"), "type": fit.get("kind"), "length_m": fit.get("length_m")})
    return rows


def dim_sum_mm_from_svg(svg: str) -> int:
    import re

    m = re.search(r"dim_sum_mm=(\d+)", svg)
    return int(m.group(1)) if m else -1
