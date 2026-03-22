"""HiveCenter LSP (Language Server Protocol) Lite Modülü: Semantik Arama ve Referans Bulucu"""
import os
import re
import subprocess
from typing import List

def find_references(workspace_root: str, symbol: str) -> str:
    """
    Ripgrep kullanarak verilen sembolün (fonksiyon/sınıf) kullanıldığı yerleri 
    sadece string eşleşmesi olarak değil, kod bloğu bağlamıyla birlikte bulur.
    Gerçek bir LSP'nin lightweight bir simülasyonudur.
    """
    try:
        # Ripgrep yüklü mü kontrol et
        if not subprocess.run(["rg", "--version"], capture_output=True).returncode == 0:
            pass # Fallback to builtin mechanisms if needed, but assuming rg is used in tools.py
    except FileNotFoundError:
        return "LSP Hata: 'rg' (ripgrep) komutu sistemde bulunamadı. Referans araması yapılamıyor."

    # Sembolün tanımına gitme (def symbol, class symbol, const symbol=, let symbol= vs.)
    definition_patterns = f"(def {symbol}|class {symbol}|const {symbol}\\s*=|function {symbol})"
    
    try:
        # Sadece bağlamı göstermek için 2 satır öncesi ve sonrası (-C 2)
        res = subprocess.run(
            ["rg", "-n", "-C", "1", symbol, workspace_root],
            capture_output=True, text=True, timeout=15
        )
        
        out = res.stdout or ""
        if not out.strip():
            return f"Sembol '{symbol}' projedeki hiçbir dosyada bulunamadı."
            
        # Parse and group by file
        grouped = {}
        current_file = "Unknown"
        lines = out.split("\n")
        
        for line in lines:
            if not line.strip() or line == "--":
                continue
            
            # rg usually outputs: file.py-10-context OR file.py:11:match
            m = re.match(r"^([^:-]+)[:\-]([0-9]+)[:\-](.*)$", line)
            if m:
                fname, lnum, content = m.groups()
                # Clean absolute path to relative for readability
                rel_name = os.path.relpath(fname, workspace_root) if fname.startswith(workspace_root) else fname
                
                if rel_name not in grouped:
                    grouped[rel_name] = []
                
                # Check if it looks like a definition vs usage
                is_def = re.search(definition_patterns, content)
                marker = "[DEFINITION] " if is_def else ""
                
                grouped[rel_name].append(f"  L{lnum}: {marker}{content.strip()}")

        result_str = f"LSP Referans Taraması ('{symbol}'):\n"
        for fname, snippets in list(grouped.items())[:15]: # Sınırla
            result_str += f"\nFile: {fname}\n" + "\n".join(snippets)
            
        if len(grouped) > 15:
            result_str += f"\n\n... (Daha fazla dosya var, toplam {len(grouped)} dosyada eşleşme bulundu)"
            
        return result_str

    except subprocess.TimeoutExpired:
        return "LSP Referans araması zaman aşımına uğradı (Çok büyük proje!)."
    except Exception as e:
        return f"LSP Çalışma Hatası: {str(e)}"
