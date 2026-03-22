import json
import time
import uuid
from typing import Any, Dict, Optional

def redact_text(s: str, enabled: bool) -> str:
    if not enabled or not s:
        return s
    out = s
    try:
        import re
        for pat, repl in [
            (r"(?i)(apikey|api_key|secret|token|password)\s*[:=]\s*[^\s]{4,}", "[REDACTED]"),
            (r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----", "[REDACTED_BLOCK]"),
        ]:
            out = re.sub(pat, repl, out)
    except Exception:
        pass
    return out[:200000]


class AuditLogger:
    def __init__(self, path: str, redact: bool = True):
        self.path = path
        self.redact = redact

    def append(self, entry: Dict[str, Any]) -> None:
        entry = dict(entry)
        entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        entry.setdefault("id", str(uuid.uuid4()))
        if "detail" in entry and isinstance(entry["detail"], str):
            entry["detail"] = redact_text(entry["detail"], self.redact)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
