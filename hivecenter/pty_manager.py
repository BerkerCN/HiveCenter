import subprocess
import threading
import uuid
from typing import Dict, Optional

class ProcessWrapper:
    def __init__(self, cmd: str, cwd: str):
        self.cmd = cmd
        self.id = uuid.uuid4().hex[:8]
        self.proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1, # Line buffered for immediate reading
        )
        self.output_buffer = []
        self.lock = threading.Lock()
        self.has_alarm = False
        self.last_alarm_snippet = ""
        
        # Start background reader thread
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()

    def _reader(self):
        try:
            for line in iter(self.proc.stdout.readline, ''):
                if line:
                    with self.lock:
                        self.output_buffer.append(line)
                        if len(self.output_buffer) > 2000:
                            self.output_buffer.pop(0) # Keep last 2000 lines
                        
                        # V19 Event-Driven Alarm Logic
                        lower_line = line.lower()
                        if "traceback (most recent" in lower_line or "fatal error" in lower_line or "cannot find module" in lower_line or "segmentation fault" in lower_line:
                            self.has_alarm = True
                            self.last_alarm_snippet = line.strip()
        except Exception:
            pass

    def read_output(self, clear: bool = True) -> str:
        with self.lock:
            out = "".join(self.output_buffer)
            if clear:
                self.output_buffer.clear()
            return out

    def write(self, data: str):
        if self.proc.poll() is None and self.proc.stdin:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except Exception:
                pass

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()

class PtyManager:
    """Manages long-running interactive background processes for the agent."""
    def __init__(self):
        self.processes: Dict[str, ProcessWrapper] = {}

    def start(self, cmd: str, cwd: str) -> str:
        pw = ProcessWrapper(cmd, cwd)
        self.processes[pw.id] = pw
        return pw.id

    def read(self, pid: str) -> Optional[str]:
        if pid in self.processes:
            out = self.processes[pid].read_output(clear=True)
            if self.processes[pid].proc.poll() is not None:
                out += f"\n[Process exited with code {self.processes[pid].proc.returncode}]"
            return out
        return None

    def write(self, pid: str, data: str) -> bool:
        if pid in self.processes:
            # Otomatik newline ekleyerek enter'a basmayı sümüle et
            self.processes[pid].write(data + "\n")
            return True
        return False
        
    def stop(self, pid: str) -> bool:
        if pid in self.processes:
            self.processes[pid].stop()
            del self.processes[pid]
            return True
        return False
        
    def stop_all(self):
        for pid in list(self.processes.keys()):
            self.stop(pid)

    def pull_alarms(self) -> list[str]:
        alarms = []
        for pid, pw in self.processes.items():
            if getattr(pw, "has_alarm", False):
                alarms.append(f"🚨 [PTY EVENT ALARM] Arka plan sürecin (PID: {pid} CMD: {pw.cmd}) çöktü veya kritik hata verdi: '{pw.last_alarm_snippet}'. Kodu düzelt ve sunucuyu yeniden başlat ([PTY: stop] ve [PTY: start] ile!).")
                pw.has_alarm = False
        return alarms

# Singleton global instance for agent tool bindings
GLOBAL_PTY = PtyManager()
