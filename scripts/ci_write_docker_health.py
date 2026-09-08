#!/usr/bin/env python3
"""Write docker_health.json from values another process measured (curl / docker).

No defaults: every field is required. Inventing 200/401/sha256 is forbidden.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write measured docker_health.json")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--health-status", required=True, type=int)
    parser.add_argument("--health-body", required=True, help="path to curl /health body")
    parser.add_argument("--tools-unauth", required=True, type=int)
    parser.add_argument("--tools-auth", required=True, type=int)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--out", default="artifacts/ci/docker_health.json")
    args = parser.parse_args()
    body_raw = Path(args.health_body).read_text(encoding="utf-8")
    try:
        health_body: object = json.loads(body_raw)
    except json.JSONDecodeError:
        health_body = body_raw
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "sha": args.sha,
        "health_status": args.health_status,
        "health_body": health_body,
        "tools_unauth_status": args.tools_unauth,
        "tools_auth_status": args.tools_auth,
        "image_digest": args.image_digest,
    }
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
