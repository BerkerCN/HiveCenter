import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

STATE_DIR = ".hive"


def state_dir(workspace_root: str) -> str:
    d = os.path.join(workspace_root, STATE_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def new_run_id() -> str:
    return str(uuid.uuid4())


def path_for_run(workspace_root: str, run_id: str) -> str:
    return os.path.join(state_dir(workspace_root), f"run_{run_id}.json")


def save_run(workspace_root: str, run_id: str, data: Dict[str, Any]) -> None:
    data = dict(data)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["run_id"] = run_id
    p = path_for_run(workspace_root, run_id)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def load_run(workspace_root: str, run_id: str) -> Optional[Dict[str, Any]]:
    p = path_for_run(workspace_root, run_id)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_recent_runs(workspace_root: str, limit: int = 30) -> List[Dict[str, Any]]:
    d = os.path.join(workspace_root, STATE_DIR)
    if not os.path.isdir(d):
        return []
    files = [f for f in os.listdir(d) if f.startswith("run_") and f.endswith(".json")]
    paths = [os.path.join(d, f) for f in files]
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    out: List[Dict[str, Any]] = []
    for p in paths[:limit]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            fn = os.path.basename(p)
            rid = data.get("run_id") or fn[4:-5]
            out.append(
                {
                    "run_id": rid,
                    "goal": (data.get("goal") or "")[:200],
                    "phase": data.get("phase"),
                    "iteration": data.get("iteration"),
                    "updated_at": data.get("updated_at"),
                    "last_perfection": data.get("last_perfection"),
                }
            )
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return out
