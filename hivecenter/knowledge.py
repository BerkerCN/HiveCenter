"""HiveCenter RAG (Retrieval-Augmented Generation) Knowledge Base Modülü."""
import os
import json
import math
import urllib.request
from typing import List, Dict

def get_knowledge_file():
    base = os.environ.get("HIVECENTER_PROJECT_PATH")
    if base and os.path.isabs(base):
        d = os.path.join(base, ".hivecenter_db")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "knowledge.json")
    return os.path.expanduser("~/.hivecenter_knowledge.json")

def get_embedding(text: str) -> List[float]:
    try:
        data = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:11434/api/embeddings", data=data, headers={"Content-Type": "application/json"})
        opt = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
        return opt.get("embedding", [])
    except Exception:
        # Fallback to local python hash if embedding fails (just to avoid complete crash on offline non-nomic setups)
        # Note: real RAG needs embeddings.
        return [float(ord(c)) for c in text[:100]] + [0.0]*(768 - min(100, len(text)))

def cosine_similarity(a: List[float], b: List[float]) -> float:
    # Handle length mismatch (fallback)
    min_len = min(len(a), len(b))
    if min_len == 0: return 0.0
    
    a = a[:min_len]
    b = b[:min_len]
    
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a * mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

def add_knowledge(concept: str, text: str) -> str:
    vec = get_embedding(concept + " " + text)
    db = []
    kf = get_knowledge_file()
    if os.path.exists(kf):
        try:
            with open(kf, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = []
            
    new_item = {"concept": concept, "text": text, "vector": vec, "links": []}
    db.append(new_item)
    
    # Auto-Link Graph Edges (V20 Graph-RAG)
    for item in db[:-1]:
        c1 = item["concept"].lower()
        c2 = concept.lower()
        if c1 in text.lower() and item["concept"] not in new_item["links"]:
            new_item["links"].append(item["concept"])
        if c2 in item.get("text", "").lower() and concept not in item.setdefault("links", []):
            item["links"].append(concept)
            
    with open(get_knowledge_file(), "w", encoding="utf-8") as f:
        json.dump(db, f) 
    return f"✅ GRAPH-RAG: The concept '{concept}' has been mapped into the neural graph. Attached edges: {new_item['links']}"

def query_knowledge(query: str, top_k: int = 3) -> str:
    kf = get_knowledge_file()
    if not os.path.exists(kf):
        return "Knowledge base is empty. Read the web and use [KNOWLEDGE_ADD] to train yourself."
    try:
        with open(kf, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return "Knowledge base file is corrupted."
        
    if not db:
        return "Knowledge base is empty."
        
    qvec = get_embedding(query)
    scored = []
    for item in db:
        score = cosine_similarity(qvec, item.get("vector", []))
        scored.append((score, item))
        
    scored.sort(key=lambda x: x[0], reverse=True)
    res = []
    for s, item in scored[:top_k]:
        if s > 0.35:  # Similarity threshold
            out_txt = f"--- GRAPH-RAG NEURAL RECALL: {item['concept']} (Similarity: {s:.2f}) ---\n{item['text']}\n"
            links = item.get("links", [])
            if links:
                linked_texts = []
                for ln in links:
                    for d in db:
                        if d["concept"] == ln:
                            linked_texts.append(f"[{ln}]: {d.get('text', '')[:120]}...")
                            break
                if linked_texts:
                    out_txt += "-> GRAPH EDGES (Related Concepts):\n" + "\n".join(linked_texts)
            res.append(out_txt)
            
    if not res:
        return f"No relevant persistent knowledge found in your neural graph for '{query}'."
    return "\n\n".join(res)
