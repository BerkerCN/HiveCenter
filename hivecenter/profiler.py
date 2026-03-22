"""HiveCenter Profiler (Ghost Mode): Kodların yavaş noktalarını ölçümleyerek ajana sunar."""
import subprocess

def profile_script(script_path: str, ws: str) -> str:
    """Belirtilen python betiğini cProfile ile çalıştırır ve en çok zaman alan (bottleneck) fonksiyonları listeler."""
    # -s tottime: Hangi fonksiyonun TOPLAMDA en fazla zaman aldığını sıralar.
    res = subprocess.run(["python", "-m", "cProfile", "-s", "tottime", script_path], cwd=ws, capture_output=True, text=True)
    
    if res.returncode == 0:
        lines = res.stdout.split("\n")
        # Çıktı genelde binlerce satır olur, SADECE en tepe (en yavaş) 25 satırı ajana veriyoruz.
        top_lines = "\n".join(lines[:25])
        return f"CPROFILE PERFORMANCE RESULTS (Top Yavaş Fonksiyonlar):\n{top_lines}\n... (kısaltıldı)"
    
    return f"PROFILER ERROR: Profil analizinde script çöktü. Hata:\n{res.stderr}"
