"""
V8.0 The Singularity: Auto-Immune System (Bağışıklık Sistemi)
Çöken bir sunucu (Node, Python vb) veya fırlatılan bir Exception olduğunda 
ajan sisteminin bu çöküşü saniyesinde yakalayıp, Nexus'tan bir "Fixer Agent" kopyalayarak
hasarı arkaplanda (kullanıcıya sormadan) onarmasını sağlar.
"""
import threading
import time
import os
import glob
from hivecenter.nexus import spawn_sub_agent

class GuardDaemon(threading.Thread):
    def __init__(self, workspace: str):
        super().__init__(daemon=True)
        self.workspace = workspace
        self.running = True

    def run(self):
        print("\\n[IMMUNITY] Gelişmiş Bağışıklık Kalkanı Devrede. Workspace taranıyor...")
        while self.running:
            time.sleep(5)
            # Scan for any .crash dump files in the workspace
            crash_dumps = glob.glob(os.path.join(self.workspace, "**", "*.crash"), recursive=True)
            for crash_file in crash_dumps:
                try:
                    with open(crash_file, "r") as f:
                        err_log = f.read()
                    
                    # Auto repair logic triggers here
                    print(f"\\n[IMMUNITY ALERT] '{crash_file}' dosyasında kritik bir çökme tespit edildi! Nöbetçi ajan uyandırılıyor...")
                    goal = f"URGENT CRASH DETECTED IN LOG: \\n{err_log}\\nFix the error immediately so the server stops crashing."
                    
                    # Spawn healing agent silently
                    spawn_sub_agent("Healer/Debugger", goal, self.workspace)
                    
                    # Rename to .crash.healing to prevent infinite healing loops
                    os.rename(crash_file, crash_file + ".healing")
                except Exception:
                    pass

def activate_immune_system(workspace: str):
    daemon = GuardDaemon(workspace)
    daemon.start()
    return daemon
