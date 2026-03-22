"""
V8.0 The Singularity: Nexus (Sub-Agent Spawning)
Ajanın kendi sistemini kopyalayarak asenkron (paralel) alt-ajanlar yaratmasını ve devasa projelerde
Frontend / Backend gibi yükleri paylaştırmasını sağlar.
"""
import threading
import queue
import time
import os

# Message queue for inter-agent communication
_HIVE_QUEUE = queue.Queue()
_SPAWNED_AGENTS = {}

def spawn_sub_agent(role: str, goal: str, workspace: str) -> str:
    """
    Spawns an independent sub-agent in a background thread to accomplish a specific part
    of the main objective. It bypasses the synchronous bottleneck.
    """
    agent_id = f"{role.replace(' ', '_').upper()}_{int(time.time()*1000)}"
    
    def _agent_worker():
        from hivecenter.llm_client import call_ollama_role, load_config
        cfg = load_config()
        model = cfg.get("models", {}).get("coder", "qwen2.5-coder:14b")
        
        system_prompt = (
            f"You are a Sub-Agent of the HiveCenter Nexus.\\n"
            f"Your Role: {role}\\n"
            f"Your Workspace: {workspace}\\n\\n"
            "You run in the background. Write purely valid code for your goal. Do NOT use conversational text.\\n"
            "Return the solution wrapped inside a ```python or ```javascript block."
        )
        
        # Simulate agent execution time & LLM call
        time.sleep(1) 
        result = call_ollama_role("coder", model, goal, system_prompt)
        
        _HIVE_QUEUE.put({
            "agent_id": agent_id,
            "role": role,
            "result": result
        })
        print(f"\\n[NEXUS AGI] Sub-Agent '{role}' successfully finished its parallel task!")

    # Spawn and track
    t = threading.Thread(target=_agent_worker, daemon=True)
    _SPAWNED_AGENTS[agent_id] = t
    t.start()
    
    return f"NEXUS ACTIVATED: Sub-Agent '{role}' (ID: {agent_id}) has been spawned in a parallel dimension and is currently hunting for: '{goal}'. It will report back soon."


def check_nexus_queue() -> str:
    """
    Drains the inter-agent message queue and returns all completed results.
    Called by tools or automatically.
    """
    results = []
    while not _HIVE_QUEUE.empty():
        msg = _HIVE_QUEUE.get_nowait()
        results.append(f"--- Sub-Agent ({msg['role']}) Report ---\\n{msg['result']}")
        
    if results:
        return "\\n\\n".join(results)
    return "NEXUS STATUS: Sub-agents are currently computing..."
