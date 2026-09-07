#!/usr/bin/env python3
"""Thin agent REPL: loop tool calls from a JSONL script of demo turns.

Each JSONL line:
  {"tool": "ingest_dexpi", "arguments": {}}
  {"tool": "query_graph", "arguments": {"tag_id": "120-VEPR-2010"}}
  {"comment": "optional note - skipped"}

No LLM required - deterministic replay for demos/CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from threadforge.agent_tools import TOOL_REGISTRY, call_tool, list_tools  # noqa: E402


def _resolve_args(args: dict) -> dict:
    """Resolve relative fixture/output paths against project ROOT."""
    out = dict(args)
    for key in ("path", "output_dir"):
        if key in out and out[key]:
            cand = Path(str(out[key]))
            if not cand.is_absolute():
                rooted = ROOT / cand
                if rooted.exists() or key == "output_dir":
                    out[key] = str(rooted)
    return out


def run_jsonl(path: Path, verbose: bool = True) -> list[dict]:
    results: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        turn = json.loads(line)
        if "comment" in turn and "tool" not in turn:
            if verbose:
                print(f"[{lineno}] # {turn['comment']}")
            continue
        tool = turn["tool"]
        args = _resolve_args(turn.get("arguments") or turn.get("args") or {})
        if verbose:
            print(f"[{lineno}] -> {tool}({json.dumps(args, default=str)})")
        try:
            out = call_tool(tool, args)
            ok = True
            err = None
        except Exception as exc:  # noqa: BLE001 - surface to script runner
            out = None
            ok = False
            err = str(exc)
            if verbose:
                print(f"    ✗ {err}")
        entry = {"line": lineno, "tool": tool, "arguments": args, "ok": ok, "result": out, "error": err}
        results.append(entry)
        if verbose and ok:
            # Compact summary
            if isinstance(out, dict):
                keys = [k for k in ("ok", "summary", "count", "activity_count", "flagged_count",
                                    "allowed", "message", "output_dir", "maturity") if k in out]
                brief = {k: out[k] for k in keys}
                print(f"    ✓ {json.dumps(brief, default=str)[:300]}")
            else:
                print(f"    ✓ {type(out).__name__}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ThreadForge agent JSONL REPL")
    parser.add_argument("script", nargs="?", default=str(Path(__file__).parent / "demo_turns.jsonl"))
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.list_tools:
        print(json.dumps(list_tools(), indent=2))
        return 0
    path = Path(args.script)
    if not path.exists():
        print(f"Script not found: {path}", file=sys.stderr)
        return 1
    results = run_jsonl(path, verbose=not args.quiet)
    failed = [r for r in results if not r["ok"]]
    print(f"\nDone: {len(results)} turns, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
