"""Ollama /api/embeddings ile basit semantik dosya sıralaması (kosinüs, stdlib)."""
import json
import math
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SKIP_DIRS = {".git", ".hive", "venv", ".venv", "node_modules", "__pycache__", "dist", "build"}
TEXT_EXT = {
    ".py",
    ".md",
    ".json",
    ".toml",
    ".txt",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".yaml",
    ".yml",
    ".sh",
    ".rs",
    ".go",
}


def ollama_embed(model: str, text: str, base_url: str = "http://localhost:11434") -> Optional[List[float]]:
    url = f"{base_url.rstrip('/')}/api/embeddings"
    payload = json.dumps({"model": model, "prompt": text[:32000]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            data = json.loads(res.read().decode("utf-8"))
        emb = data.get("embedding")
        if isinstance(emb, list) and emb:
            return [float(x) for x in emb]
    except Exception:
        return None
    return None


def cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _iter_text_files(
    root: str,
    max_files: int,
    max_file_bytes: int,
) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if len(out) >= max_files:
                return out
            ext = os.path.splitext(name)[1].lower()
            if ext not in TEXT_EXT:
                continue
            fp = os.path.join(dirpath, name)
            try:
                st = os.path.getsize(fp)
                if st > max_file_bytes:
                    continue
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    chunk = f.read(min(8000, max_file_bytes))
                rel = os.path.relpath(fp, root)
                out.append((rel, chunk))
            except OSError:
                continue
    return out


def index_workspace_files(workspace_root: str, model: str, cfg: Dict[str, Any]) -> str:
    max_files = int(cfg.get("max_files_scan", 200)) # Increased for batch indexing
    max_file_bytes = int(cfg.get("max_file_bytes", 120_000))
    
    files = _iter_text_files(workspace_root, max_files, max_file_bytes)
    if not files:
        return "INDEX_WORKSPACE: No text files found to index."
        
    db = []
    success_count = 0
    
    for rel, chunk in files:
        # Simple chunking for big files
        t_emb = ollama_embed(model, chunk[:6000])
        if t_emb:
            db.append({
                "file": rel,
                "content": chunk[:6000],
                "vector": t_emb
            })
            success_count += 1
            
    index_path = os.path.join(workspace_root, ".hivecenter_workspace_index.json")
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(db, f)
        return f"✅ WORKSPACE INDEXED: Successfully embedded {success_count} files into the Codebase RAG."
    except Exception as e:
        return f"INDEX_WORKSPACE ERROR: Could not save index to {index_path} ({e})"

def query_workspace_index(workspace_root: str, query: str, model: str, cfg: Dict[str, Any]) -> str:
    top_k = int(cfg.get("top_k", 10))
    q = query.strip()
    if not q:
        return "CODEBASE_QUERY: empty query"
        
    index_path = os.path.join(workspace_root, ".hivecenter_workspace_index.json")
    if not os.path.exists(index_path):
        return "CODEBASE_QUERY: Workspace is not indexed yet! Run [INDEX_WORKSPACE] first."
        
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return "CODEBASE_QUERY: Index file corrupted. Run [INDEX_WORKSPACE] again."
        
    q_emb = ollama_embed(model, q)
    if not q_emb:
        return "CODEBASE_QUERY: error embedding failed (model running?)"
        
    scored = []
    for item in db:
        s = cosine(q_emb, item.get("vector", []))
        scored.append((s, item.get("file", "unknown"), item.get("content", "")[:350]))
        
    scored.sort(key=lambda x: -x[0])
    lines = [f"CODEBASE_QUERY top-{top_k} results for '{q}':"]
    for s, rel, prev in scored[:top_k]:
        if s > 0.30: # Semantic threshold
            clean_prev = prev.replace("\n", " ").strip()
            lines.append(f"  [{s:.2f}] {rel}\n     {clean_prev}...")
            
    if len(lines) == 1:
        return f"CODEBASE_QUERY: No highly relevant files found for '{q}'."
    return "\n".join(lines)
