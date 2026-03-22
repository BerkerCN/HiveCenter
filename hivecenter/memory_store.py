import json
import os
import time
from typing import Any, Dict

DEFAULT_MEM = {"version": 1, "entries": []}


def memory_path(workspace_root: str) -> str:
    return os.path.join(workspace_root, "memory.json")


def read_memory(workspace_root: str) -> Dict[str, Any]:
    p = memory_path(workspace_root)
    if not os.path.isfile(p):
        return dict(DEFAULT_MEM)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def append_entry(workspace_root: str, entry: Dict[str, Any], max_entries: int = 200) -> Dict[str, Any]:
    p = memory_path(workspace_root)
    data = read_memory(workspace_root)
    ent = dict(entry)
    ent.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    data.setdefault("entries", [])
    data["entries"].append(ent)
    data["entries"] = data["entries"][-max_entries:]
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return data
