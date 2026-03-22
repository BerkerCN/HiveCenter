"""CursorMaster (veya uyumlu) skill kütüphanesi: skills_index.json ile arama, SKILL.md okuma."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


def _split_query_words(s: str) -> List[str]:
    return [x for x in re.split(r"[^\w\-]+", s, flags=re.UNICODE) if x]

_index_cache: Optional[List[Dict[str, Any]]] = None
_index_root: Optional[str] = None


def _expand(p: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(p)))


def _load_index(root: str) -> List[Dict[str, Any]]:
    global _index_cache, _index_root
    r = _expand(root)
    if _index_cache is not None and _index_root == r:
        return _index_cache
    idx_path = os.path.join(r, "skills_index.json")
    if not os.path.isfile(idx_path):
        _index_cache, _index_root = [], r
        return []
    try:
        with open(idx_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        _index_cache, _index_root = [], r
        return []
    _index_cache = data if isinstance(data, list) else []
    _index_root = r
    return _index_cache


def _safe_under_root(root: str, relpath: str) -> Tuple[Optional[str], str]:
    root_abs = _expand(root)
    if not root_abs or not os.path.isdir(root_abs):
        return None, "cursor_master root not found or not a directory"
    rel = relpath.strip().replace("\\", "/").lstrip("/")
    for part in rel.split("/"):
        if part == "..":
            return None, "path traversal"
    cand = _expand(os.path.join(root_abs, rel))
    if cand != root_abs and not cand.startswith(root_abs + os.sep):
        return None, "path outside cursor_master root"
    return cand, ""


def skill_search(cfg: Dict[str, Any], query: str, limit: int = 22) -> str:
    if not cfg.get("enabled", True):
        return "CURSORMASTER: devre dışı (cursor_master.enabled=false)."
    root = (cfg.get("root") or "").strip()
    if not root:
        return "CURSORMASTER: config.json içinde cursor_master.root ayarlayın (örn. ~/Projeler/CursorMaster)."
    root_abs = _expand(root)
    if not os.path.isdir(root_abs):
        return f"CURSORMASTER: kök dizin yok: {root_abs}"

    entries = _load_index(root_abs)
    if not entries:
        return "CURSORMASTER: skills_index.json bulunamadı veya boş."

    q = query.lower().strip()
    words = [w for w in _split_query_words(q) if len(w) > 1]
    if not words:
        words = [q] if q else []

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        blob = " ".join(
            str(e.get(k, "") or "") for k in ("id", "name", "description", "category", "path")
        ).lower()
        score = 0
        for w in words:
            if w and w in blob:
                score += 1
        if score > 0:
            scored.append((score, e))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("id", ""))))
    top = [e for _, e in scored[:limit]]

    lines: List[str] = []
    for e in top:
        sid = str(e.get("id", ""))
        desc = (e.get("description") or "").replace("\n", " ")[:220]
        cat = e.get("category") or ""
        lines.append(f"- {sid} [{cat}] — {desc}")

    if not lines:
        return (
            "CURSORMASTER: eşleşme yok. Daha kısa anahtar kelimeler deneyin "
            "(örn. pytest, react, security, zod)."
        )
    return "CURSORMASTER SKILL_SEARCH:\n" + "\n".join(lines)


def skill_read(cfg: Dict[str, Any], spec: str) -> Tuple[str, bool]:
    if not cfg.get("enabled", True):
        return "CURSORMASTER: devre dışı.", False
    root = (cfg.get("root") or "").strip()
    if not root:
        return "CURSORMASTER: cursor_master.root ayarlı değil.", False
    max_b = int(cfg.get("max_skill_bytes", 120000) or 120000)

    root_abs = _expand(root)
    if not os.path.isdir(root_abs):
        return f"CURSORMASTER: kök yok: {root_abs}", False

    spec = spec.strip()
    if not spec:
        return "CURSORMASTER: SKILL_READ için id veya path gerekli.", False

    abs_path: Optional[str] = None

    if "/" in spec or spec.endswith(".md"):
        rel = spec
        if not rel.lower().endswith(".md"):
            rel = rel.rstrip("/") + "/SKILL.md"
        p, err = _safe_under_root(root, rel)
        if err:
            return f"CURSORMASTER READ: {err}", False
        abs_path = p
    else:
        skill_id = spec
        entries = _load_index(root_abs)
        rel_path: Optional[str] = None
        for e in entries:
            if isinstance(e, dict) and str(e.get("id", "")) == skill_id:
                rel_path = str(e.get("path") or "").strip()
                break
        if not rel_path:
            return f"CURSORMASTER: skill id bulunamadı: {skill_id!r} (önce SKILL_SEARCH kullanın).", False
        rel = f"{rel_path}/SKILL.md"
        p, err = _safe_under_root(root, rel)
        if err:
            return f"CURSORMASTER READ: {err}", False
        abs_path = p

    if not abs_path or not os.path.isfile(abs_path):
        return f"CURSORMASTER: dosya yok: {abs_path}", False

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        return f"CURSORMASTER READ: {e}", False

    b = raw.encode("utf-8", errors="replace")
    if len(b) > max_b:
        raw = b[:max_b].decode("utf-8", errors="replace") + "\n... [CURSORMASTER: çıktı kısaltıldı]"

    return f"CURSORMASTER SKILL_READ ({os.path.basename(os.path.dirname(abs_path))})\n---\n{raw}", True
