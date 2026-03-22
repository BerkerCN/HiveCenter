import subprocess
from typing import Any, Dict, Optional, Tuple


def run_verify_command(
    cmd: Optional[str],
    cwd: str,
    timeout_sec: int,
    max_output_bytes: int,
) -> Tuple[bool, str, Optional[int]]:
    """Doğrulama komutu (ör. pytest). Dönüş: (passed, output_summary, exit_code)."""
    if not cmd or not str(cmd).strip():
        return True, "(verify skipped: no test_command)", None
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=max(timeout_sec, 5),
        )
        out = (res.stdout or "") + (res.stderr or "")
        if len(out.encode("utf-8", errors="replace")) > max_output_bytes:
            out = out[:max_output_bytes] + "\n... [truncated]"
        ok = res.returncode == 0
        return ok, out, res.returncode
    except subprocess.TimeoutExpired:
        return False, f"VERIFY TIMEOUT after {timeout_sec}s", -1
    except Exception as e:
        return False, f"VERIFY ERROR: {e}", -1
