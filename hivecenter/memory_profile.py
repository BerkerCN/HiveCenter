"""HiveCenter Kalıcı Hafıza: Kullanıcı alışkanlıklarını oturumlar arası saklar."""
import os
import json

PROFILE_PATH = os.path.expanduser("~/.hivecenter_profile.json")

def load_profile() -> list:
    if not os.path.exists(PROFILE_PATH):
        return []
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_profile(memories: list):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)

def remember(fact: str) -> str:
    mem = load_profile()
    if fact not in mem:
        mem.append(fact)
        save_profile(mem)
        return f"Permanent Memory SAVED: {fact}"
    return "Fact is already permanently deeply registered."

def forget(fact: str) -> str:
    mem = load_profile()
    if fact in mem:
        mem.remove(fact)
        save_profile(mem)
        return f"Permanent Memory FORGOTTEN: {fact}"
    return "Fact was not found in permanent memory."
