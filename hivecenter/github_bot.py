"""HiveCenter GitHub Bot: Github CLI (gh) kullanarak izole otonomi sağlar."""
import subprocess
import uuid

def read_issue(issue_id: str, ws: str) -> str:
    res = subprocess.run(["gh", "issue", "view", issue_id], cwd=ws, capture_output=True, text=True)
    if res.returncode == 0:
        return f"GITHUB ISSUE #{issue_id}:\n{res.stdout}"
    return f"GITHUB HATA (gh issue view): {res.stderr}\nNot: Sistemde 'gh' kurulu ve login olunmuş mu?"

def create_pr(title: str, ws: str) -> str:
    branch = f"hive-auto-{uuid.uuid4().hex[:6]}"
    
    # 1. Yeni branch aç
    subprocess.run(["git", "checkout", "-b", branch], cwd=ws, capture_output=True)
    # 2. Add ve Commit
    subprocess.run(["git", "add", "."], cwd=ws, capture_output=True)
    commit = subprocess.run(["git", "commit", "-m", title], cwd=ws, capture_output=True, text=True)
    if "nothing to commit" in commit.stdout:
        return "GITHUB PR İPTAL: Commit edilecek hiçbir değişiklik yok."
        
    # 3. Push
    push = subprocess.run(["git", "push", "-u", "origin", branch], cwd=ws, capture_output=True, text=True)
    
    # 4. PR Yarat
    res = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", "Bu PR, HiveCenter (V6 Enterprise Agent) kullanılarak otonom olarak oluşturulmuştur."], 
        cwd=ws, capture_output=True, text=True
    )
    
    if res.returncode == 0:
        return f"GITHUB PR OLUŞTURULDU BAŞARIYLA:\n{res.stdout}"
    return f"GITHUB PR HATA: {res.stderr}\nGit Push Log: {push.stderr}"
