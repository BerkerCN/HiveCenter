"""Onaylı bile olsa asla çalıştırılmayacak komut kalıpları (son çare güvenlik)."""
from typing import List, Tuple

# Küçük sabit liste; config shell.hard_deny_substrings ile genişletilir
_BUILTIN_HARD = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    ">/dev/sd",
    "chmod 777 /",
]


def is_hard_denied(cmd: str, extra: List[str]) -> Tuple[bool, str]:
    low = cmd.strip().lower()
    for d in _BUILTIN_HARD + list(extra or []):
        if d and str(d).strip().lower() in low:
            return True, f"hard_denied:{d!r}"
    return False, ""
