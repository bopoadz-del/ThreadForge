"""Minimal MCP stdio server exposing ThreadForge agent_tools."""
from __future__ import annotations

import json
import sys
from typing import Any

from threadforge import agent_tools


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": (fn.__doc__ or name).strip().splitlines()[0],
            "inputSchema": {"type": "object", "additionalProperties": True},
        }
        for name, fn in sorted(agent_tools.TOOL_REGISTRY.items())
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    if name not in agent_tools.TOOL_REGISTRY:
        raise KeyError(name)
    return agent_tools.TOOL_REGISTRY[name](**(arguments or {}))


def handle_message(msg: dict[str, Any]) -> dict[str, Any]:
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": list_tools()}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = call_tool(str(name), args if isinstance(args, dict) else {})
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        out = handle_message(msg)
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
