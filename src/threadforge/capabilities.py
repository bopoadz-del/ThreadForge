"""REAL / STUB / WALL capability register — source for generated README table."""
from __future__ import annotations

from typing import TypedDict


class Capability(TypedDict):
    name: str
    status: str
    notes: str


CAPABILITIES: list[Capability] = [
    {"name": "DEXPI/Proteus-shaped XML parse", "status": "REAL", "notes": "Lite + rich + TrainingTestCases; XSD via xmlschema"},
    {"name": "Topology graph", "status": "REAL", "notes": "Tags / lines / from-to / BL"},
    {"name": "A* routing + clash", "status": "REAL", "notes": "Capsule math; IFC-in AABB"},
    {"name": "PCF writer", "status": "REAL", "notes": "Contiguous PIPE/ELBOW; ISOGEN cert WALL"},
    {"name": "Iso SVG/PDF + GA", "status": "REAL", "notes": "30° heuristic — not ISOGEN stamped"},
    {"name": "Hydrotest B31.3 345.4.2", "status": "REAL", "notes": "Capped by B16.5 Table 2-1.1"},
    {"name": "AWP IWP release + XER/MSPDI", "status": "REAL", "notes": "Vendored MSPDI XSD"},
    {"name": "FastAPI + MCP + Alembic registry", "status": "REAL", "notes": "SQLite+Postgres; RBAC 3 roles"},
    {"name": "Vendor DEXPI extensions / live APIs", "status": "WALL", "notes": "See WALLS.md"},
    {"name": "Web 3D viewer / Gantt UI", "status": "OUT OF SCOPE", "notes": "Data + tools only"},
]


def capability_table() -> str:
    lines = [
        "| Capability | Status | Notes |",
        "|---|---|---|",
    ]
    for row in CAPABILITIES:
        lines.append(f"| {row['name']} | **{row['status']}** | {row['notes']} |")
    return "\n".join(lines)
