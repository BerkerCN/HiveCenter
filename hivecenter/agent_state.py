"""workspace/AGENT_STATE.md — uzun koşularda dönem özeti (insan + ajan okunabilir)."""
import os
import time
from typing import Optional


def append_iteration(
    workspace_root: str,
    run_id: str,
    iteration: int,
    perfection: int,
    one_line_summary: str,
) -> None:
    path = os.path.join(workspace_root, "AGENT_STATE.md")
    line = (
        f"- {time.strftime('%Y-%m-%d %H:%M:%S')} | iter {iteration} | run `{run_id[:8]}…` | "
        f"PERFECTION {perfection} | {one_line_summary[:300]}\n"
    )
    try:
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("# HiveCenter agent state log\n\n")
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def read_tail(workspace_root: str, max_bytes: int = 4000) -> Optional[str]:
    path = os.path.join(workspace_root, "AGENT_STATE.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
