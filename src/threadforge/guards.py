"""Upload size, XML-bomb, and rate-limit guards (B34)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB — measured reject above this
RATE_LIMIT_N = 20
RATE_LIMIT_WINDOW_S = 2.0

_HITS: dict[str, Deque[float]] = defaultdict(deque)
_LOCK = Lock()


class GuardError(ValueError):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def reject_xml_bomb(data: bytes) -> None:
    """Reject DTD / entity expansion bombs before parse.

    Measured: presence of ``<!DOCTYPE`` or ``<!ENTITY`` (case-insensitive) in the
    leading 64 KiB, or payload larger than ``MAX_UPLOAD_BYTES``.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise GuardError("upload_too_large", f"payload {len(data)} > {MAX_UPLOAD_BYTES}", 413)
    head = data[:65536].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise GuardError("xml_bomb", "DOCTYPE/ENTITY declaration refused", 400)


def check_upload_size(n: int) -> None:
    if n > MAX_UPLOAD_BYTES:
        raise GuardError("upload_too_large", f"content-length {n} > {MAX_UPLOAD_BYTES}", 413)


def rate_limit_hit(key: str, now: float | None = None) -> bool:
    """Return True if this hit is over the limit (should 429)."""
    t = now if now is not None else time.monotonic()
    with _LOCK:
        q = _HITS[key]
        cutoff = t - RATE_LIMIT_WINDOW_S
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= RATE_LIMIT_N:
            return True
        q.append(t)
        return False


def reset_rate_limits() -> None:
    with _LOCK:
        _HITS.clear()
