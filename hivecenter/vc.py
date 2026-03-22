"""HiveCenter Versiyon Kontrol Sistemi (Git Otopilotu)"""
import os
import subprocess

def auto_commit(workspace: str, run_id: str, iteration: int) -> bool:
    """Ajan kodlamaya başlamadan önce tüm projeyi güvenceye alır."""
    try:
        # Klasörde .git yoksa başlat
        if not os.path.exists(os.path.join(workspace, ".git")):
            subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
            # Kullanıcı adı ve email geçici ayarı (git commit için şarttır)
            subprocess.run(["git", "config", "user.email", "agent@hivecenter.local"], cwd=workspace, capture_output=True)
            subprocess.run(["git", "config", "user.name", "HiveCenter Agent"], cwd=workspace, capture_output=True)

        subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
        
        # Sadece değişiklik varsa commit at, yoksa hata verir
        res = subprocess.run(
            ["git", "commit", "-m", f"Auto-commit: Run {run_id} Iteration {iteration}"],
            cwd=workspace,
            capture_output=True
        )
        return True
    except Exception as e:
        print(f"Auto-commit error: {e}")
        return False

def revert_last(workspace: str) -> str:
    """Kodu bir önceki çalışan iterasyona geri döndürür."""
    if not os.path.exists(os.path.join(workspace, ".git")):
        return "ERROR: No Git repository found to revert."
    try:
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=workspace, capture_output=True, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=workspace, capture_output=True, check=True)
        return "SUCCESS: Codebase has been successfully reverted to the previous iteration."
    except Exception as e:
        return f"ERROR: Failed to revert code. {e}"
