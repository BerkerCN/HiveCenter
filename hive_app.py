import os
import sys
import time
import signal
import subprocess
import atexit
import shutil

def main():
    print("Starting HiveCenter...")
    
    base_dir = os.path.abspath(os.path.dirname(__file__))
    server_cmd = [sys.executable, "bin/hive_server.py"]
    
    log_file = open(os.path.join(base_dir, "hive_server.log"), "a")
    
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=base_dir,
        preexec_fn=os.setsid,
        stdout=log_file,
        stderr=subprocess.STDOUT
    )
    
    def cleanup():
        print("Shutting down HiveCenter (stopping server process group)...")
        try:
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        except Exception:
            pass
            
    atexit.register(cleanup)
    time.sleep(2.5)
    html_path = "http://127.0.0.1:5001/dashboard/index.html"
    
    chrome_bin = (
        shutil.which("google-chrome") or 
        shutil.which("chromium-browser") or 
        shutil.which("chromium") or 
        shutil.which("google-chrome-stable") or 
        shutil.which("brave-browser") or 
        shutil.which("microsoft-edge")
    )

    if chrome_bin:
        print(f"Opening dashboard in app mode ({os.path.basename(chrome_bin)})...")
        app_data_dir = os.path.join(base_dir, ".chrome_app_data")
        os.makedirs(app_data_dir, exist_ok=True)
        
        gui_proc = subprocess.Popen([
            chrome_bin, 
            f"--app={html_path}", 
            f"--user-data-dir={app_data_dir}",
            "--window-size=1350,900",
            "--class=HiveCenter"
        ])
        
        try:
            gui_proc.wait() 
            print("Window closed; stopping server...")
        except KeyboardInterrupt:
            gui_proc.terminate()
            
    else:
        print("No Chrome/Chromium found; opening default browser...")
        import webbrowser
        webbrowser.open(html_path)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
            
if __name__ == "__main__":
    main()
