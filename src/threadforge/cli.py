"""ThreadForge demo CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from threadforge import agent_tools as tools


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="threadforge", description="ThreadForge EPC digital-thread CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest DEXPI/Proteus XML")
    p_ingest.add_argument("--path", default=None)

    p_query = sub.add_parser("query", help="Query topology graph")
    p_query.add_argument("--tag-id")
    p_query.add_argument("--summary", action="store_true")

    p_revise = sub.add_parser("revise", help="Revise a tag or line")
    p_revise.add_argument("entity_type", choices=["tag", "pipeline", "line", "equipment"])
    p_revise.add_argument("entity_id")
    p_revise.add_argument("--set", nargs=2, action="append", metavar=("KEY", "VALUE"), default=[])

    sub.add_parser("cascade", help="Re-run dirty generators")
    sub.add_parser("test-packs", help="Build test packs")
    sub.add_parser("work-packages", help="Build work packages")

    p_sched = sub.add_parser("schedule", help="Attach schedule JSON/CSV")
    p_sched.add_argument("path")

    p_la = sub.add_parser("look-ahead", help="Look-ahead window")
    p_la.add_argument("--weeks", type=int, default=3)

    sub.add_parser("co-activity", help="Co-activity check")

    p_mat = sub.add_parser("maturity", help="Maturity gate check")
    p_mat.add_argument("--required", default="IFC")

    p_pipe = sub.add_parser("pipeline", help="Run pipeline stage(s)")
    p_pipe.add_argument("--stage", default="outputs")
    p_pipe.add_argument("--all", action="store_true")

    sub.add_parser("demo", help="Run full demo sequence")
    sub.add_parser("tools", help="List agent tools")

    args = parser.parse_args(argv)

    if args.cmd == "tools":
        _print(tools.list_tools())
        return 0

    if args.cmd == "demo":
        from demos.run_demo import run as run_demo

        run_demo()
        return 0

    if args.cmd == "ingest":
        _print(tools.ingest_dexpi(args.path))
        return 0

    # Ensure ingest for other commands if needed
    if tools.SESSION.graph is None and args.cmd != "ingest":
        tools.ingest_dexpi()

    if args.cmd == "query":
        filters = {}
        if args.tag_id:
            filters["tag_id"] = args.tag_id
        if args.summary or not filters:
            filters["summary"] = True
        _print(tools.query_graph(**filters))
    elif args.cmd == "revise":
        updates = {k: v for k, v in args.set}
        _print(tools.revise_pid(args.entity_type, args.entity_id, updates))
    elif args.cmd == "cascade":
        _print(tools.cascade_rerun())
    elif args.cmd == "test-packs":
        _print(tools.build_test_packs())
    elif args.cmd == "work-packages":
        _print(tools.build_work_packages())
    elif args.cmd == "schedule":
        _print(tools.attach_schedule(args.path))
    elif args.cmd == "look-ahead":
        _print(tools.look_ahead(weeks=args.weeks))
    elif args.cmd == "co-activity":
        _print(tools.co_activity_check())
    elif args.cmd == "maturity":
        _print(tools.maturity_check(required=args.required))
    elif args.cmd == "pipeline":
        _print(tools.run_pipeline_stage(args.stage, run_all=args.all))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    # Allow running without install by adding src to path
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    raise SystemExit(main())
