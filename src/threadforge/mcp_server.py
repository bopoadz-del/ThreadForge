"""MCP stdio server: tools + threadforge://job/{id}/{kind} resources."""
from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import urlparse

from threadforge import agent_tools
from threadforge.persist import artefact_payload

RESOURCE_SCHEME = "threadforge"


def _db_url() -> str:
    from threadforge.server import current_db_url

    return current_db_url()


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


def parse_job_resource(uri: str) -> tuple[str, str]:
    """threadforge://job/{id}/{kind} → (job_id, kind)."""
    raw = urlparse(uri)
    if raw.scheme != RESOURCE_SCHEME:
        raise ValueError(f"unsupported scheme {raw.scheme}")
    host = raw.netloc or raw.path.lstrip("/").split("/")[0]
    parts = [p for p in ((raw.path or "").split("/")) if p]
    if host == "job":
        if len(parts) < 2:
            raise ValueError("threadforge://job/{id}/{kind}")
        return parts[0], parts[1]
    if parts and parts[0] == "job" and len(parts) >= 3:
        return parts[1], parts[2]
    raise ValueError(f"not a job resource: {uri}")


def resource_uri(job_id: str, kind: str) -> str:
    return f"{RESOURCE_SCHEME}://job/{job_id}/{kind}"


def list_resources(job_id: str | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine, text

    url = _db_url()
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if job_id:
                rows = conn.execute(
                    text("SELECT DISTINCT job_id, kind FROM artefacts WHERE job_id=:j ORDER BY kind"),
                    {"j": job_id},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT DISTINCT job_id, kind FROM artefacts ORDER BY job_id, kind")
                ).fetchall()
    finally:
        engine.dispose()
    return [
        {
            "uri": resource_uri(str(jid), str(kind)),
            "name": f"{jid}/{kind}",
            "mimeType": "application/octet-stream",
        }
        for jid, kind in rows
    ]


def read_resource(uri: str) -> dict[str, Any]:
    job_id, kind = parse_job_resource(uri)
    payload = artefact_payload(_db_url(), job_id, kind)
    if payload is None:
        raise KeyError(uri)
    data, digest, media = payload
    return {
        "uri": uri,
        "mimeType": media,
        "blob": data,
        "sha256": digest,
        "bytes": len(data),
    }


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
    if method == "resources/list":
        params = msg.get("params") or {}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"resources": list_resources(params.get("job_id"))},
        }
    if method == "resources/read":
        params = msg.get("params") or {}
        uri = str(params.get("uri") or "")
        try:
            body = read_resource(uri)
            # JSON-RPC cannot carry raw bytes; expose sha256 + hex
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "uri": body["uri"],
                    "mimeType": body["mimeType"],
                    "sha256": body["sha256"],
                    "bytes": body["bytes"],
                    "blob_hex": body["blob"].hex() if isinstance(body["blob"], bytes) else "",
                },
            }
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
