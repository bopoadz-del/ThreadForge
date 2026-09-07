#!/usr/bin/env python3
"""Dump live OpenAPI and diff against the committed openapi.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadforge.server import export_openapi  # noqa: E402


def main() -> int:
    dumped = Path("/tmp/openapi-fresh.json")
    fresh = json.loads(export_openapi(dumped).read_text(encoding="utf-8"))
    committed = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
    if fresh != committed:
        print("openapi dump/diff FAIL")
        print(f"fresh paths={sorted(fresh.get('paths', {}))}")
        print(f"committed paths={sorted(committed.get('paths', {}))}")
        return 1
    print("openapi dump/diff PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
