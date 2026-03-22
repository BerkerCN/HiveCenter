"""Ollama HTTP çağrıları ve model çıktısı son işleme."""
import json
import re
import urllib.request
from typing import Any, Dict, Optional

# DeepSeek-R1 / benzeri "thinking" blokları (araç çıktısını kirletmesin diye temizlenir)
_RE_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_RE_THINK_FENCE = re.compile(r"```(?:think|reasoning|Thought)\s*\n[\s\S]*?```", re.DOTALL)
_RE_PLAIN_THINK = re.compile(
    r"^\s*(?:Reasoning|Thought|Thinking)\s*:\s*[\s\S]*?(?=\n(?:[^\n]*\[|[A-Z]{2,})|\Z)",
    re.IGNORECASE | re.MULTILINE,
)


def strip_reasoning_tags(text: str, enabled: bool = True) -> str:
    if not enabled or not text:
        return text or ""
    t = _RE_THINK_BLOCK.sub("", text)
    t = _RE_THINK_FENCE.sub("", t)
    t = _RE_PLAIN_THINK.sub("", t)
    return t.strip()


def _build_options(ollama_cfg: Dict[str, Any], role: str) -> Dict[str, Any]:
    opts: Dict[str, Any] = {}
    base = dict(ollama_cfg or {})
    for k in ("temperature", "top_p", "top_k", "repeat_penalty", "num_ctx", "num_predict"):
        if k in base and base[k] is not None:
            opts[k] = base[k]
    ro = base.get(role)
    if isinstance(ro, dict):
        for k, v in ro.items():
            if v is not None and k not in ("note", "description"):
                opts[k] = v
    return opts


def ollama_generate(
    ollama_cfg: Dict[str, Any],
    model: str,
    prompt: str,
    system: str = "",
    role: str = "default",
) -> str:
    url = "http://127.0.0.1:11434/api/generate"
    options = _build_options(ollama_cfg or {}, role)
    data: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "system": system or "",
        "stream": False,
    }
    if options:
        data["options"] = options
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as res:
            return json.loads(res.read().decode("utf-8")).get("response", "")
    except Exception as e:
        return f"ERROR: {str(e)}"


def truncate_observation(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head - 40
    return (
        text[:head]
        + "\n\n... [middle truncated for context budget] ...\n\n"
        + text[-tail:]
    )


def observation_has_failures(obs: str) -> bool:
    low = (obs or "").lower()
    return any(
        x in low
        for x in (
            "failed",
            "policy:",
            "error:",
            "not found",
            "denied",
            "timeout",
            "approval required",
        )
    )
