"""
V6.0 AGI Feature: GraphRAG Memory System.
Stores concepts as a Directed Graph (Nodes and Edges) instead of just pure text vectors.
"""
import os
import json
from typing import List, Dict, Any

def get_graph_file():
    base = os.environ.get("HIVECENTER_PROJECT_PATH")
    if base and os.path.isabs(base):
        d = os.path.join(base, ".hivecenter_db")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "graph.json")
    return os.path.expanduser("~/.hivecenter_graph.json")


class MemoryGraph:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, str]] = []
        self._load()

    def _load(self):
        gf = get_graph_file()
        if os.path.exists(gf):
            try:
                with open(gf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.nodes = data.get("nodes", {})
                    self.edges = data.get("edges", [])
            except Exception:
                pass

    def _save(self):
        with open(get_graph_file(), "w", encoding="utf-8") as f:
            json.dump({"nodes": self.nodes, "edges": self.edges}, f, indent=2)

    def add_node(self, node_id: str, node_type: str, content: str):
        node_id = node_id.strip().lower()
        self.nodes[node_id] = {"type": node_type, "content": content}
        self._save()

    def add_edge(self, source: str, relation: str, target: str):
        source = source.strip().lower()
        target = target.strip().lower()
        relation = relation.strip().upper()
        # Prevent duplicates
        for e in self.edges:
            if e["source"] == source and e["target"] == target and e["relation"] == relation:
                return
        self.edges.append({"source": source, "relation": relation, "target": target})
        self._save()

    def query(self, node_id: str, depth: int = 1) -> str:
        """Returns a string description of a node and its immediate neighborhood."""
        node_id = node_id.strip().lower()
        if node_id not in self.nodes:
            # Try partial matching
            matches = [nid for nid in self.nodes if node_id in nid]
            if not matches:
                return f"No memories found for '{node_id}'."
            node_id = matches[0]

        out = []
        node = self.nodes[node_id]
        out.append(f"CONCEPT: {node_id} (Type: {node['type']})\\nDETAILS: {node['content']}\\n")
        
        related = []
        for e in self.edges:
            if e["source"] == node_id:
                related.append(f"  - IT {e['relation']} -> {e['target']}")
            elif e["target"] == node_id:
                related.append(f"  - {e['source']} -> {e['relation']} IT")
        
        if related:
            out.append("RELATIONSHIPS:")
            out.extend(related)
        return "\\n".join(out)


def auto_extract_graph(concept_name: str, text: str):
    """Uses LLM to extract triplets from the provided text and builds the Graph."""
    from hivecenter.llm_client import call_ollama_role, load_config
    cfg = load_config()
    model = cfg.get("models", {}).get("inspector", "qwen2.5-coder:14b")
    
    prompt = (
        f"Extract knowledge graph triplets from the following text regarding '{concept_name}'.\\n"
        f"TEXT:\\n{text}\\n\\n"
        "Return ONLY lines in the exact format: [SOURCE] | [RELATION] | [TARGET]\\n"
        "Example:\\n"
        "vite | CAUSES | vite not found error\\n"
        "vite not found error | SOLVED_BY | using cd sub_dir\\n"
        "Keep relations uppercase and nodes short."
    )
    
    response = call_ollama_role("inspector", model, prompt, "You are a Knowledge Graph extractor. Output only triplets.")
    
    graph = MemoryGraph()
    graph.add_node(concept_name, "Concept", text[:200] + "..." if len(text)>200 else text)
    
    relations_added = 0
    for line in response.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            src, rel, tgt = parts
            graph.add_node(src, "Entity", "")
            graph.add_node(tgt, "Entity", "")
            graph.add_edge(src, rel, tgt)
            relations_added += 1
            
    return f"GraphRAG updated. Added '{concept_name}' and extrapolated {relations_added} neural connections."

def query_graph_memory(query_term: str) -> str:
    graph = MemoryGraph()
    return graph.query(query_term)
