"""İnsan onayı kuyruğu: JSONL (dashboard / API ile yönetim)."""
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _path(workspace_root: str) -> str:
    d = os.path.join(workspace_root, ".hive", "approvals")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "queue.jsonl")


def _read_all(workspace_root: str) -> List[Dict[str, Any]]:
    p = _path(workspace_root)
    if not os.path.isfile(p):
        return []
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_all(workspace_root: str, rows: List[Dict[str, Any]]) -> None:
    p = _path(workspace_root)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def add_pending(workspace_root: str, run_id: str, command: str, kind: str = "shell") -> str:
    aid = str(uuid.uuid4())
    rec = {
        "id": aid,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "command": command[:4000],
        "kind": kind,
        "status": "pending",
    }
    p = _path(workspace_root)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return aid


def list_pending(workspace_root: str) -> List[Dict[str, Any]]:
    return [r for r in _read_all(workspace_root) if r.get("status") == "pending"]


def list_all(workspace_root: str, limit: int = 200) -> List[Dict[str, Any]]:
    rows = _read_all(workspace_root)
    return rows[-limit:]


def get_record(workspace_root: str, approval_id: str) -> Optional[Dict[str, Any]]:
    for r in _read_all(workspace_root):
        if r.get("id") == approval_id:
            return r
    return None


def list_approved_ready(workspace_root: str) -> List[Dict[str, Any]]:
    """Onaylandı ama henüz çalıştırılmadı."""
    out = []
    for r in _read_all(workspace_root):
        if r.get("status") == "approved" and not r.get("executed_at"):
            out.append(r)
    return out


def mark_executed(
    workspace_root: str,
    approval_id: str,
    returncode: int,
    output: str,
    ok: bool,
) -> Tuple[bool, str]:
    rows = _read_all(workspace_root)
    found = False
    for r in rows:
        if r.get("id") == approval_id:
            r["status"] = "executed"
            r["executed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            r["execution_returncode"] = returncode
            r["execution_ok"] = ok
            r["execution_output"] = (output or "")[:16000]
            found = True
            break
    if not found:
        return False, "id not found"
    _write_all(workspace_root, rows)
    return True, "ok"


def resolve(workspace_root: str, approval_id: str, approved: bool) -> Tuple[bool, str]:
    rows = _read_all(workspace_root)
    found = False
    for r in rows:
        if r.get("id") == approval_id:
            r["status"] = "approved" if approved else "rejected"
            r["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            found = True
            break
    if not found:
        return False, "id not found"
    _write_all(workspace_root, rows)
    return True, "ok"


def add_manual_request(workspace_root: str, run_id: Optional[str], command: str, note: str = "") -> str:
    aid = str(uuid.uuid4())
    rec = {
        "id": aid,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id or "",
        "command": command[:4000],
        "kind": "manual",
        "note": note[:2000],
        "status": "pending",
    }
    p = _path(workspace_root)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return aid
