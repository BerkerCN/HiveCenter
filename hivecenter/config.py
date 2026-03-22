import copy
import json
import os
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "version": 1,
    "workspace_root": "~/Projeler/HiveCenter/workspace",
    "allowed_roots": ["~/Projeler/HiveCenter/workspace"],
    "forbidden_path_substrings": [".ssh", "/etc/", "/root/", "/sys/", "/proc/"],
    "read_max_bytes": 786432,
    "shell": {
        "approval_triggers": ["apt ", "dnf ", "pacman "],
        "execute_approved_timeout_sec": 300,
        "hard_deny_substrings": [],
        "timeout_sec": 600,
        "max_output_bytes": 393216,
        "deny_substrings": [
            "rm -rf /",
            "mkfs",
            "dd if=",
            ":(){ :|:& };:",
            "curl ",
            "wget ",
            "sudo ",
            "su -",
            "chmod 777 /",
            ">/dev/sd",
        ],
    },
    "run": {
        "max_iterations": 16,
        "perfection_threshold": 72,
    },
    "verify": {
        "test_command": None,
        "require_pass_for_done": False,
    },
    "models": {
        "architect": "deepseek-r1:8b",
        "coder": "qwen2.5-coder:14b",
        "inspector": "deepseek-r1:8b",
        "coder_fallback_8gb": "qwen2.5-coder:7b",
    },
    "audit": {
        "log_path": "logs/audit.ndjson",
        "redact": True,
    },
    "search": {
        "max_matches": 120,
        "timeout_sec": 25,
    },
    "glob": {
        "max_matches": 320,
    },
    "patch": {
        "enabled": True,
    },
    "semantic": {
        "enabled": True,
        "embed_model": "nomic-embed-text",
        "max_files_scan": 64,
        "max_file_bytes": 150000,
        "top_k": 14,
    },
    "ollama": {
        "temperature": 0.35,
        "top_p": 0.92,
        "num_ctx": 8192,
        "num_predict": 6144,
        "request_timeout_sec": 900,
        "strip_reasoning_tags": True,
        "architect": {"temperature": 0.42, "num_ctx": 8192, "num_predict": 6144},
        "coder": {"temperature": 0.18, "num_ctx": 8192, "num_batch": 256, "num_predict": 8192},
        "inspector": {"temperature": 0.28, "num_ctx": 8192, "num_predict": 4096},
    },
    "autonomy": {
        "max_observation_chars": 28000,
        "append_agent_state_md": True,
        "inject_agent_state_tail": True,
        "agent_state_max_bytes": 6000,
    },
    "hints": {
        "ollama_pull_coder": "ollama pull qwen2.5-coder:14b",
        "ollama_if_oom": "VRAM yetmezse: models.coder -> qwen2.5-coder:7b veya ollama.coder.num_ctx -> 4096; OLLAMA_NUM_CTX=4096.",
        "ollama_cpu_offload": "Model tam sığmazsa Ollama katmanları CPU'ya taşır; swap faydalı olabilir.",
    },
    "cursor_master": {
        "enabled": True,
        "root": "~/Projeler/CursorMaster",
        "max_skill_bytes": 120000,
        "search_max": 22,
    },
    "ui": {
        "goal_templates": [],
    },
}


def _expand_user(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def load_config(repo_root: str) -> Dict[str, Any]:
    path = os.path.join(repo_root, "config.json")
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)

        def deep_merge(base: dict, over: dict) -> dict:
            for k, v in over.items():
                if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
            return base

        deep_merge(cfg, user)

    cfg["workspace_root"] = _expand_user(cfg["workspace_root"])
    cfg["allowed_roots"] = [_expand_user(x) for x in cfg.get("allowed_roots", [])]
    cm = cfg.get("cursor_master")
    if isinstance(cm, dict) and cm.get("root"):
        cm["root"] = _expand_user(str(cm["root"]))
    os.makedirs(cfg["workspace_root"], exist_ok=True)
    audit_rel = cfg.get("audit", {}).get("log_path", "logs/audit.ndjson")
    log_abs = os.path.join(cfg["workspace_root"], audit_rel)
    os.makedirs(os.path.dirname(log_abs), exist_ok=True)
    cfg["_repo_root"] = repo_root
    cfg["_audit_log_abs"] = log_abs
    return cfg
