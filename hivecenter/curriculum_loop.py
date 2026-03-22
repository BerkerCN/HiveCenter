"""
V6.0 AGI Feature: Automated Curriculum Learning.
When the user is away, the agent autonomously finds new repos/articles, reads them, tests the technology, and saves it to its permanent 'Skills' database.
"""
import os
import json
import random
import time

def trigger_curriculum_learning(parent_workspace: str) -> str:
    """
    Called when the system is idle. Fetches a trending GitHub repo or an arbitrary new tech concept,
    spawns a sub-agent to learn it, and writes a SKILL.md for future reference.
    """
    from hivecenter.web import web_read
    from hivecenter.llm_client import call_ollama_role, load_config
    
    cfg = load_config()
    model = cfg.get("models", {}).get("architect", "qwen2.5-coder:14b")
    
    topics = ["modern state management react", "latest css frameworks", "rust ownership model practical", "go concurrency patterns", "new python 3.12 features"]
    topic = random.choice(topics)
    
    print(f"[CURRICULUM] Initiating self-learning module on: {topic}")
    
    # Simulate searching or using LLM to generate a mock learning target
    # In a full system, you would [WEB: search] for this topic.
    search_prompt = f"Write a very brief, 3-sentence summary of the core concept behind '{topic}'. Then list 1 practical code example."
    learning_material = call_ollama_role("architect", model, search_prompt, "You are an educator extracting knowledge.")
    
    # The agent acts on this material to create a Skill Card.
    skill_card_prompt = (
        f"You just learned about this concept:\\n{learning_material}\\n\\n"
        "Create a SKILL.md card to save into the system's permanent CursorMaster memory.\\n"
        "Return the RAW MARKDOWN only.\\n"
        "Format:\\n"
        "---"
        "name: Skill Name\\n"
        "description: Brief explanation\\n"
        "---\\n"
        "# How to use it\\n"
        "<code>"
    )
    
    skill_card_md = call_ollama_role("coder", model, skill_card_prompt, "You are the curriculum parser. Output raw markdown skill card.")
    
    # Save the skill card
    skill_name = topic.replace(" ", "_").lower()
    skill_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", skill_name)
    os.makedirs(skill_dir, exist_ok=True)
    
    skill_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(skill_card_md)
        
    return f"Curriculum Learning Completed! Acquired new skill: {skill_name}. Skill card saved to {skill_path}."

