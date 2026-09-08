#!/usr/bin/env python3
"""Dump live OpenAPI JSON to a path (standing gate: dump then diff)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadforge.server import export_openapi  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: dump_openapi.py DEST.json", file=sys.stderr)
        return 2
    dest = Path(sys.argv[1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    export_openapi(dest)
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
