"""
V7.0 God-Mode: Chronos (Auto-Rollback & Time Travel)
Sistemin CREATE, REPLACE, SHELL gibi komutlardan önce otomatik olarak dosya yedekleri almasını ve 
hata yapıldığında saniyesinde geçmişe (Ctrl+Z) dönmesini sağlar.
"""
import os
import shutil
import time

def get_chronos_dir(workspace: str) -> str:
    path = os.path.join(workspace, ".hive_chronos")
    os.makedirs(path, exist_ok=True)
    return path

def take_snapshot(workspace: str, file_path: str):
    """
    Takes a snapshot of a single file before it is modified.
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return
        
    chronos_dir = get_chronos_dir(workspace)
    
    # We store the latest backup of a file as <filename>_snapshot.bak
    rel_path = os.path.relpath(file_path, workspace)
    safe_name = rel_path.replace("/", "_").replace("\\\\", "_") + "_snapshot.bak"
    
    backup_path = os.path.join(chronos_dir, safe_name)
    shutil.copy2(file_path, backup_path)
    
    # Record the last modified file in a registry
    registry = os.path.join(chronos_dir, "last_action.txt")
    with open(registry, "w", encoding="utf-8") as f:
        f.write(f"{file_path}|{backup_path}")

def revert_time(workspace: str) -> str:
    """
    Reverts the very last file modification using the Chronos registry.
    """
    chronos_dir = get_chronos_dir(workspace)
    registry = os.path.join(chronos_dir, "last_action.txt")
    
    if not os.path.exists(registry):
        return "[CHRONOS ERROR] No time-travel history found in registry."
        
    try:
        with open(registry, "r", encoding="utf-8") as f:
            data = f.read().strip()
            
        if not data:
            return "[CHRONOS ERROR] Registry is empty."
            
        original_file, backup_file = data.split("|")
        
        if not os.path.exists(backup_file):
            return f"[CHRONOS ERROR] Backup snapshot missing for {original_file}."
            
        shutil.copy2(backup_file, original_file)
        
        # Clear registry to prevent loop reverting unless we want deep history
        os.remove(registry)
        
        return f"CHRONOS REVERT SUCCESSFUL! Time turned back. The file `{original_file}` has been restored to its previous state."
        
    except Exception as e:
        return f"[CHRONOS FATAL ERROR] Timeline corrupted: {e}"
