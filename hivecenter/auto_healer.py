"""HiveCenter Auto-Healer V2.0 (Self-Healing CI): Hataları otonom olarak onaran akıllı motor."""
import re
import os
import subprocess

def check_and_heal(ws: str, cmd: str, out: str) -> tuple[bool, str]:
    """
    SHELL çıktısını analiz eder. Basit bağımlılık hatalarını doğrudan sübvanse eder.
    Karmaşık 'Traceback' veya kod hatalarında Coder LLM'ine danışır (Infinite Debug).
    """
    # 1. Hızlı Basit Bağımlılık Tespiti (Regex)
    m_py = re.search(r"ModuleNotFoundError: No module named '([^']+)'", out)
    if m_py:
        pkg = m_py.group(1)
        res = subprocess.run(["pip", "install", pkg], cwd=ws, capture_output=True, text=True)
        return True, f"Auto-Healer intercepted module crash. Installed python package '{pkg}':\n{res.stdout[-200:]}"
        
    m_node = re.search(r"Error: Cannot find module '([^']+)'", out)
    if m_node:
        pkg = m_node.group(1)
        if not pkg.startswith('.'):
            pkg_base = pkg.split('/')[0] if not pkg.startswith('@') else '/'.join(pkg.split('/')[:2])
            res = subprocess.run(["npm", "install", pkg_base], cwd=ws, capture_output=True, text=True)
            return True, f"Auto-Healer intercepted missing node_module. Installed npm package '{pkg_base}':\n{res.stdout[-200:]}"

    # 2. Akıllı Karmaşık Hata Tespiti (LLM-Powered Self Healing CI)
    error_keywords = ["Traceback (most recent call last)", "SyntaxError:", "TypeError:", "Error:", "fatal:", "FAILED", "Exception:"]
    has_error = any(k in out for k in error_keywords)
    
    # Bazı istisnaları (uyarıları) atla
    if out.strip().endswith("warnings.") or "DeprecationWarning" in out:
        has_error = False
        
    if has_error:
        # Kodcu modelini ayarlardan çek
        try:
            from hivecenter.llm_client import load_config, call_ollama_role
            cfg = load_config()
            coder_model = cfg.get("coder_model", "llama3.1:8b")
            
            prompt = (
                f"Sistemdeki BİR HATA TETİKLENDİ. Çalıştırılan komut: `{cmd}`\n\n"
                f"=== ÇIKTI VE HATA LOGU ===\n{out[-2500:]}\n==========================\n\n"
                "Sen otonom bir hata onarım uzmanısın. Yukarıdaki hatanın nedenini tespit et ve "
                "kodu düzeltmek için SADECE aşağıdaki formatta [REPLACE] veya zorunluysa [SHELL] "
                "XML bloklarını kullan. Hiçbir açıklama yazma, sadece kod onarım aracını output olarak ver.\n\n"
                "Kullanım Örneği:\n"
                "[REPLACE: src/main.py]\n"
                "<<<< SEARCH\n"
                "hatali = kod()\n"
                "====\n"
                "hatasiz = kod()\n"
                ">>>> REPLACE\n"
            )
            
            system_msg = "You are the Auto-Healer sub-system. Fix crashes autonomously. Output only tool tags."
            # Ajanı yardıma çağırıyoruz
            llm_response = call_ollama_role(role="coder", model=coder_model, prompt=prompt, system=system_msg)
            
            # Gelen cevaptan yamaları çıkar (Patch Application Regex)
            applied_any = False
            heal_log_buffer = []
            
            # REPLACE yamalarını uygula
            from hivecenter.patch_apply import apply_search_replace
            for m in re.finditer(r"\[\s*REPLACE\s*:\s*([^\]]+?)\s*\]\s*<<<<\s*SEARCH\s*\r?\n(.*?)====(?:\r?\n)?(.*?)>>>>\s*REPLACE", llm_response, re.DOTALL | re.IGNORECASE):
                rel_hint = m.group(1).strip()
                search_body = m.group(2)
                replace_body = m.group(3)
                
                ok, msg = apply_search_replace(ws, rel_hint, search_body, replace_body)
                if ok:
                    applied_any = True
                    heal_log_buffer.append(f"Auto-Healer yamaladı: {rel_hint}")
                else:
                    heal_log_buffer.append(f"Auto-Healer yama başarısız ({rel_hint}): {msg[:100]}")
                    
            # Belki yeni bir dosya oluşturmak istedi
            for m in re.finditer(r"\[\s*CREATE\s*:\s*([^\]]+?)\s*\].*?```[a-zA-Z0-9_-]*\s*\r?\n(.*?)```", llm_response, re.DOTALL | re.IGNORECASE):
                rel = m.group(1).strip()
                content = m.group(2)
                path = os.path.join(ws, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                applied_any = True
                heal_log_buffer.append(f"Auto-Healer oluşturdu: {rel}")
                
            # Belki bir SHELL onarımı yapmak istedi (örn: chmod +x)
            for m in re.finditer(r"\[\s*SHELL\s*:\s*([^\]]+)\s*\]", llm_response, re.IGNORECASE):
                fix_cmd = m.group(1).strip()
                res = subprocess.run(fix_cmd, shell=True, capture_output=True, text=True, cwd=ws)
                applied_any = True
                heal_log_buffer.append(f"Auto-Healer komut çalıştırdı: {fix_cmd} -> Kod: {res.returncode}")

            if applied_any:
                return True, "Otonom Yapay Zeka Onarımı (LLM-Healer) Devrede:\n" + "\n".join(heal_log_buffer)
            else:
                return False, "" # Ajan bir şey yapamadı
                
        except Exception as e:
            return False, f"Auto-Healer LLM çağrısında hata: {e}"
            
    return False, ""
