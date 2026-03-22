import os
import re
from typing import List, Dict

# Basit regex tabanlı iskelet (skeleton) çıkarıcı
# Proje büyüdükçe Tree-Sitter'a geçirilebilir.

def _extract_signatures(filepath: str) -> List[str]:
    signatures = []
    ext = os.path.splitext(filepath)[1].lower()
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return []

    if ext in {".py"}:
        # Python class and def
        pattern = re.compile(r"^([ \t]*)(class|def)\s+([a-zA-Z0-9_]+)")
        for i, line in enumerate(lines):
            m = pattern.match(line)
            if m:
                indent = m.group(1)
                signatures.append(f"{indent}{line.strip()}")
                
    elif ext in {".js", ".ts", ".jsx", ".tsx"}:
        # JS/TS class, function, and arrow functions
        pattern = re.compile(r"^([ \t]*)(export\s+)?(default\s+)?(class|function|const\s+[a-zA-Z0-9_]+\s*=|let\s+[a-zA-Z0-9_]+\s*=)\s*([a-zA-Z0-9_]*)")
        for i, line in enumerate(lines):
            m = pattern.match(line)
            if m:
                indent = m.group(1)
                signatures.append(f"{indent}{line.strip()}")

    return signatures

def generate_repo_map(workspace_root: str, max_files: int = 150, goal: str = None) -> str:
    """Tüm projenin haritasını (sadece sınıflar ve fonksiyonlar) çıkarır."""
    ignore_dirs = {".git", ".hive", "node_modules", "venv", ".venv", "__pycache__", "build", "dist", "out", ".next"}
    valid_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs"}
    
    skeletons: Dict[str, str] = {}
    
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, workspace_root)
                sigs = _extract_signatures(filepath)
                if sigs:
                    skeletons[rel_path] = "\n".join(sigs)
                    
    if not skeletons:
        return ""

    # SMART CONTEXT PRUNING (Vector Similarity)
    if goal and len(skeletons) > 12:
        try:
            from hivecenter.embeddings import embed_text, cosine_similarity
            from hivecenter.config import load_config
            cfg = load_config()
            if cfg.get("semantic", {}).get("enabled", True):
                embed_model = cfg.get("semantic", {}).get("embed_model", "nomic-embed-text")
                goal_vec = embed_text(goal, embed_model)
                
                scored = []
                for path, skel in skeletons.items():
                    skel_vec = embed_text(f"File: {path}\n{skel}", embed_model)
                    score = cosine_similarity(goal_vec, skel_vec)
                    scored.append((score, path, skel))
                
                # Sort by highest relevance
                scored.sort(key=lambda x: x[0], reverse=True)
                
                res = "--- SMART PRUNED REPO MAP (Top Relevant Files) ---\n"
                for score, path, skel in scored[:20]: # Keep top 20 most relevant files to the goal
                    res += f"[{path}] (Relevance: {score:.2f})\n{skel}\n"
                return res
        except Exception:
            pass # Fallback to standard alphabetical sort if Ollama embedding fails

    # STANDARD ALPHABETICAL FALLBACK
    items = sorted(list(skeletons.items()))[:max_files]
    res = "--- WORKSPACE SKELETON ---\n"
    for path, skel in items:
        res += f"[{path}]\n{skel}\n"
        
    if len(skeletons) > max_files:
        res += f"\n... (Truncated. {len(skeletons) - max_files} more files exist)\n"
        
    return res
