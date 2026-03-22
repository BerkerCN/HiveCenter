"""HiveCenter Swarm Modülü: Mimarın paralel alt-ajanlar yaratmasını sağlar."""
from typing import Any
import os

def run_sub_agent(name: str, goal: str, parent_tool_ctx: Any, max_iters: int = 3) -> str:
    """
    Kendi içinde otonom bir ReAct döngüsü çalıştıran mini coder (işçi arı).
    """
    from hivecenter.llm_client import call_ollama_role
    from hivecenter.model_io import observation_has_failures, strip_reasoning_tags
    from hivecenter.prompts import CODER_SYSTEM, build_tools_block
    from hivecenter.tools import execute_agent_tools
    from hivecenter.config import load_config

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config(repo_root)
    model = cfg.get("models", {}).get("coder", "qwen2.5-coder:14b")
    
    context = ""
    history_log = f"--- SWARM AGENT ({name}) BORN ---\nTarget: {goal}\n"
    tools_block = build_tools_block()
    
    for i in range(max_iters):
        prompt = (
            f"YOU ARE A SUB-AGENT NAMED '{name}' SPAWNED BY THE ARCHITECT.\n"
            f"YOUR GOAL: {goal}\n\n"
            f"Execute the tools required to strictly achieve this goal. You have {max_iters - i} turns left.\n"
            f"DO NOT WRITE ANY EXPLANATIONS. OUTPUT ONLY TOOL TAGS.\n\n"
            f"PAST OBSERVATIONS IN THIS SUB-TASK:\n{context}\n\n"
            f"TOOLS:\n{tools_block}"
        )
        
        raw_output = call_ollama_role("coder", model, prompt, CODER_SYSTEM)
        
        # AGI Yükseltmesi (V5.0): Multi-Agent Debate (Müzakere)
        if "[CREATE:" in raw_output.upper() or "[REPLACE:" in raw_output.upper() or "[SHELL:" in raw_output.upper():
            critic_prompt = (
                f"The Coder sub-agent '{name}' wants to execute the following actions to achieve '{goal}':\\n\\n"
                f"{raw_output}\\n\\n"
                "You are the Critic (Şeytanın Avukatı). Review this strictly. "
                "1. Is it missing any obvious unit tests?\\n"
                "2. Is it going to break the application or use arbitrary/unsafe shell commands?\\n"
                "3. Are the replacements contextually safe?\\n"
                "If PERFECT, reply exactly: 'APPROVED'. Otherwise, reply 'REJECT:' followed by why it is bad."
            )
            critic_response = call_ollama_role("inspector", model, critic_prompt, "You are the ruthless Critic. Protect the codebase.")
            if "REJECT" in critic_response.upper():
                context += f"\\nCRITIC REJECTION:\\nThe Chief Critic reviewed your proposed actions and rejected them.\\nReason:\\n{critic_response}\\n\\nRevise your tool actions immediately!\\n"
                history_log += f"\\nIter {i+1}: [DEBATE] Critic rejected the plan. Agent forced to revise.\\n"
                continue
                
        stripped_action = strip_reasoning_tags(
            raw_output, cfg.get("ollama", {}).get("strip_reasoning_tags", True)
        )
        
        if not stripped_action or "no tool invocations" in stripped_action.lower():
            history_log += f"\nIter {i+1}: Agent stopped (no tools used).\n"
            break
            
        obs = execute_agent_tools(stripped_action, parent_tool_ctx)
        
        context += f"\nACTION:\n{stripped_action}\nOBSERVATION:\n{obs}\n"
        history_log += f"\n-- ITER {i+1} --\n[ACTION]\n{stripped_action}\n[RESULT]\n{obs}\n"
        
        # Eğer kritik bir hata yoksa ve ajan işi bitirdiğini belirten bir araç kullanmadıysa loop sonlanır (şimdilik max_iters'e kadar devam eder).
        
    history_log += f"\\n--- SWARM AGENT ({name}) TERMINATED ---"
    return history_log

def run_arena_mcts(goal: str, parent_tool_ctx: Any) -> str:
    """AGI Phase 1: MCTS AlphaCoder Logic. Generates 3 paths, critic evaluates, best is executed."""
    from hivecenter.llm_client import call_ollama_role
    from hivecenter.model_io import strip_reasoning_tags
    from hivecenter.prompts import build_tools_block
    from hivecenter.tools import execute_agent_tools
    from hivecenter.config import load_config
    import concurrent.futures
    import re

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config(repo_root)
    model = cfg.get("models", {}).get("coder", "qwen2.5-coder:14b")
    tools_block = build_tools_block()
    
    # Generate 3 candidates in parallel
    prompts = [
        f"Approach A: Focus on simplicity and immediate results.\\nGoal: {goal}\\nTools available:\\n{tools_block}\\nReturn the precise [TOOL] blocks to solve this.",
        f"Approach B: Focus on robust error handling, scalability, and clean code.\\nGoal: {goal}\\nTools available:\\n{tools_block}\\nReturn the precise [TOOL] blocks.",
        f"Approach C: Focus on modern design patterns (functional or OOP) and extreme performance.\\nGoal: {goal}\\nTools available:\\n{tools_block}\\nReturn the precise [TOOL] blocks."
    ]
    
    candidates = []
    def _gen(p):
        return call_ollama_role("coder", model, p, "You are a master coder drafting a strict sequence of tools. ONLY OUTPUT TOOL TAGS, NO EXPLANATIONS.")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for out in executor.map(_gen, prompts):
            candidates.append(out)
            
    # Critic evaluates each strategy
    best_score = -1
    best_action = ""
    critic_log = "--- MCTS ARENA EVALUATION (Survival of the Fittest) ---\\n"
    
    for i, action in enumerate(candidates):
        critic_prompt = f"Evaluate this proposed tool chain for the goal '{goal}':\\n\\n{action}\\n\\nRate it strictly from 0 to 100 based on exactness, safety, and likelihood of success. Reply with ONLY a number representing the score."
        cr = call_ollama_role("inspector", model, critic_prompt, "You are an objective scorer. Output an integer from 0 to 100.")
        m = re.search(r"\\d+", cr)
        score = int(m.group(0)) if m else 0
        critic_log += f"Approach {['A (Simplicity)','B (Robustness)','C (Performance)'][i]}: {score}/100\\n"
        if score > best_score:
            best_score = score
            best_action = action
            
    critic_log += f"\\nWINNING SCORE: {best_score}/100. Executing the winning variant...\\n"
    
    stripped = strip_reasoning_tags(best_action, True)
    obs = execute_agent_tools(stripped, parent_tool_ctx)
    return critic_log + f"--- EXECUTION RESULT ---\\n{obs}"

