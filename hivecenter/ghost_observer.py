import threading
import time

class GhostObserver:
    def __init__(self):
        self.active_url = None
        self.alarms = []
        self.alarms_history = set()  # Dedup
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        
    def start_watching(self, url: str):
        with self.lock:
            self.active_url = url
            self.alarms_history.clear()
            if self.running:
                return
            self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        with self.lock:
            self.running = False
            self.active_url = None
            
    def pull_alarms(self):
        with self.lock:
            ret = list(self.alarms)
            self.alarms.clear()
            return ret

    def _watch_loop(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                def handle_console(msg):
                    if msg.type == "error":
                        with self.lock:
                            # Sadece en kritik ve farklı hataları almak için
                            err = msg.text[:200]
                            if err not in self.alarms_history and "favicon" not in err.lower():
                                self.alarms_history.add(err)
                                self.alarms.append(f"👻 [GHOST OBSERVER ALARM] Canlı Tarayıcıda (URL: {self.active_url}) Console Error yakalandı:\n{err}")
                
                page.on("console", handle_console)
                
                while self.running:
                    url = None
                    with self.lock:
                        url = self.active_url
                    if not url:
                        time.sleep(2)
                        continue
                        
                    try:
                        page.goto(url, timeout=5000)
                        time.sleep(3) # Wait for React/Vite to render
                        
                        body_text = page.locator("body").inner_text() or ""
                        if "Exception" in body_text or "Error:" in body_text:
                            # Sadece yeni hataları basmak için basit debounce
                            err_snippet = body_text[:300].strip()
                            if err_snippet not in self.alarms_history:
                                self.alarms_history.add(err_snippet)
                                with self.lock:
                                    self.alarms.append(f"👻 [GHOST OBSERVER ALARM] Ekranda kritik bir çökme metni var (Redbox / Overlay):\n{err_snippet}...\nLütfen kodu onar!")
                    except Exception:
                        pass # Sunucu henüz kalkmamış veya sayfa yüklenememiş olabilir
                    
                    time.sleep(4)
                
                browser.close()
            except Exception:
                pass

GLOBAL_GHOST = GhostObserver()
