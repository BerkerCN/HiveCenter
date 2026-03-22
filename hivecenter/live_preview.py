import os
import subprocess
import time
import re
import threading

_PREVIEWS = {}

def start_live_preview(port: str, cmd: str, ws: str) -> str:
    
    if port in _PREVIEWS:
        app_proc, ssh_proc = _PREVIEWS[port]
        try: app_proc.terminate()
        except: pass
        try: ssh_proc.terminate()
        except: pass

    # 1. Start the App
    app_proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    time.sleep(2)
    if app_proc.poll() is not None:
        out = app_proc.stdout.read()
        return f"LIVE_PREVIEW HATA: '{cmd}' komutu anında çöktü (Exit Code {app_proc.returncode}):\n{out[:500]}"
        
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-R", f"80:localhost:{port}", "nokey@localhost.run"
    ]
    ssh_proc = subprocess.Popen(
        ssh_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    _PREVIEWS[port] = (app_proc, ssh_proc)
    
    extracted_url = None
    log_buffer = []

    def _read_ssh():
        nonlocal extracted_url
        for line in ssh_proc.stdout:
            raw = line.strip()
            if raw:
                log_buffer.append(raw)
            m = re.search(r"(https?://[a-zA-Z0-9.-]+\.lhr\.life)", raw)
            if m:
                extracted_url = m.group(1)
                break
            m2 = re.search(r"([a-zA-Z0-9.-]+\.lhr\.life)", raw)
            if m2 and not extracted_url:
                extracted_url = "https://" + m2.group(1)
                break

    t = threading.Thread(target=_read_ssh, daemon=True)
    t.start()
    t.join(15.0) 
    
    if extracted_url:
        return f"✅ OTONOM CANLI YAYIN BAŞARILI!\nUygulaman şu komutla ayağa kaldırıldı: `{cmd}`\nTunel Port: {port}\n\n🌐 Canlı İnternet URL'si: {extracted_url}\n\nLütfen bu bağlantıyı [REPLY: Bağlantı] aracıyla kullanıcıya ilet."
    else:
        app_proc.terminate()
        ssh_proc.terminate()
        return f"❌ CANLI YAYIN HATASI: SSH tüneli URL veremedi. Kullanıcı limitlerine takılmış veya port meşgul olabilir.\nLoglar:\n" + "\n".join(log_buffer[-10:])
