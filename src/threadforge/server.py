"""ThreadForge HTTP API (bootstrap deploy; full modules loading)."""
from __future__ import annotations

import os
from typing import Any

def create_app():
    try:
        from fastapi import FastAPI, Header, HTTPException
    except ImportError as e:
        raise SystemExit(f"fastapi required: {e}")

    app = FastAPI(title="ThreadForge", version="1.0.0")
    tokens_raw = os.environ.get("TF_API_TOKENS", "")
    # engineer:eng-token:write,reviewer:rev-token:read
    token_map = {}
    for part in tokens_raw.split(","):
        part=part.strip()
        if not part: continue
        bits=part.split(":")
        if len(bits)>=2:
            token_map[bits[1]] = bits[0] if len(bits)==2 else bits[2]

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "threadforge", "data": os.environ.get("TF_DATA")}

    @app.get("/")
    def root() -> dict[str, Any]:
        return {"name": "ThreadForge", "docs": "/docs", "health": "/health"}

    return app
