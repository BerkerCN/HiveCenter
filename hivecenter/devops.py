"""HiveCenter DevOps: Otonom Canlı Dağıtım (Deployment) Operasyonları"""
import subprocess

def deploy_ssh(target: str, commands: str, ws: str) -> str:
    """SSH üzerinden uzaktaki bir sunucuya git pull, docker-compose up, nginx restart gibi komutları yollar."""
    res = subprocess.run(["ssh", target, commands], cwd=ws, capture_output=True, text=True)
    if res.returncode == 0:
        return f"SSH DEPLOYMENT SUCCESS:\n{res.stdout}"
    return f"SSH DEPLOYMENT FAILED:\n{res.stderr}\nNot: Kimlik doğrulamasız (SSH-Key) giriş kurulu olmalıdır."

def deploy_vercel(ws: str) -> str:
    """Next.js / React uygulamalarını tek hamlede Vercel'e canlıya atar."""
    # npx vercel kullanarak küresel kuruluma ihtiyaç duymayız.
    res = subprocess.run(["npx", "vercel", "--prod", "--yes"], cwd=ws, capture_output=True, text=True)
    if res.returncode == 0:
        return f"VERCEL DEPLOYMENT SUCCESS (Canlı Bağlantı Hazır):\n{res.stdout}"
    return f"VERCEL DEPLOYMENT FAILED:\n{res.stderr}\nNot: Sistemde 'vercel login' ile giriş yapılmış olmalıdır."
