"""Append-only audit NDJSON — son kayıtları okuma (büyük dosyada kuyruk penceresi)."""
import json
import os
from typing import Any, Dict, List

_MAX_TAIL_BYTES = 512 * 1024


def read_recent_audit_entries(path: str, limit: int = 80) -> List[Dict[str, Any]]:
    if limit < 1:
        return []
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - _MAX_TAIL_BYTES))
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
    parsed: List[Dict[str, Any]] = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(parsed) > limit:
        parsed = parsed[-limit:]
    return list(reversed(parsed))
