"""nvidia-smi ile GPU kullanım / VRAM (yoksa boş döner)."""
import re
import shutil
import subprocess
from typing import Any, Dict, Optional


def get_gpu_metrics() -> Optional[Dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode != 0 or not (res.stdout or "").strip():
            return None
        line = (res.stdout or "").strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None
        util = float(re.sub(r"[^\d.]", "", parts[0]) or 0)
        mem_u = float(re.sub(r"[^\d.]", "", parts[1]) or 0)
        mem_t = float(re.sub(r"[^\d.]", "", parts[2]) or 0)
        mem_pct = round(100.0 * mem_u / mem_t, 1) if mem_t > 0 else 0.0
        return {
            "utilization_percent": min(100.0, round(util, 1)),
            "memory_used_mb": round(mem_u, 1),
            "memory_total_mb": round(mem_t, 1),
            "memory_percent": mem_pct,
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None
