import os
import time

def is_text_file(filename: str) -> bool:
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss", ".json", ".md", ".vue", ".rs", ".go", ".java", ".c", ".cpp"}
    return any(filename.endswith(e) for e in exts)

def run_codebase_migration(ws_root: str, source_dir: str, target_instruction: str) -> str:
    from hivecenter.llm_client import load_config, call_ollama_role
    
    cfg = load_config()
    model = cfg.get("coder_model", "llama3.1:8b")
    
    abs_source = source_dir if os.path.isabs(source_dir) else os.path.join(ws_root, source_dir)
    if not os.path.exists(abs_source) or not os.path.isdir(abs_source):
        return f"[MIGRATE_ERROR] Kaynak klasör bulunamadı veya geçerli değil: {abs_source}"
        
    parent_dir = os.path.dirname(abs_source)
    base_name = os.path.basename(abs_source)
    target_dir = os.path.join(parent_dir, f"{base_name}_migrated")
    
    ignore_dirs = {"node_modules", ".git", "venv", ".venv", "__pycache__", "build", "dist", ".next"}
    
    log_buffer = [f"🚀 [AST_MIGRATOR] Devasa Proje Çevirmeni Başlatıldı!"]
    log_buffer.append(f"Kaynak: {abs_source}")
    log_buffer.append(f"Hedef Çıktı: {target_dir}")
    log_buffer.append(f"Çeviri Talimatı: '{target_instruction}'")
    log_buffer.append("-" * 40)
    
    os.makedirs(target_dir, exist_ok=True)
    
    files_to_migrate = []
    for root, dirs, files in os.walk(abs_source):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if is_text_file(file):
                files_to_migrate.append(os.path.join(root, file))
                
    if not files_to_migrate:
        return "[MIGRATE_ERROR] Klasörde çevrilecek geçerli metin/kod dosyası bulunamadı."
        
    log_buffer.append(f"Toplam {len(files_to_migrate)} dosya analiz edilecek ve sırayla yeniden yazılacak...")
    
    success_count = 0
    fail_count = 0
    
    for file_path in files_to_migrate:
        rel_path = os.path.relpath(file_path, abs_source)
        out_path = os.path.join(target_dir, rel_path)
        
        # Okyanus ötesi klasörleri aç
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            if not content.strip():
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write("")
                continue
                
            # LLM Çeviri Çağrısı
            sys_msg = (
                "You are an elite AST Transpiler and Code Migration Engine. "
                "You will receive a SINGLE FILE's content and a TARGET INSTRUCTION. "
                "You must rewrite the entire file's content according to the instruction, maintaining identical business logic. "
                "OUTPUT ONLY THE RAW TRANSLATED CODE. DO NOT use markdown blocks like ```python. DO NOT add conversational text. "
                "If the target instruction says 'Vue to React', output pure React code. "
            )
            
            prompt = (
                f"File: {rel_path}\n"
                f"Instruction: {target_instruction}\n\n"
                f"=== ORIGINAL SOURCE ===\n{content}\n=======================\n\n"
                "Output the fully translated code exactly now:"
            )
            
            translated_code = call_ollama_role(role="coder", model=model, prompt=prompt, system=sys_msg)
            
            # Markdown temizliği (Eğer model kural ihlali yaparsa)
            translated_code = translated_code.strip()
            if translated_code.startswith("```"):
                translated_code = translated_code.split("\n", 1)[-1]
                idx = translated_code.rfind("```")
                if idx != -1:
                    translated_code = translated_code[:idx]
                    
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write(translated_code.strip() + "\n")
                
            log_buffer.append(f"✅ Çevrildi: {rel_path}")
            success_count += 1
            
            # Rate limiting / Soğuma (GPU yanmasın)
            time.sleep(1)
            
        except Exception as e:
            log_buffer.append(f"❌ BAŞARISIZ ({rel_path}): {e}")
            fail_count += 1
            
    log_buffer.append("-" * 40)
    log_buffer.append(f"🎉 MIGRATION TAMAMLANDI! {success_count} dosya başarıyla çevrildi, {fail_count} hata.")
    log_buffer.append(f"Lütfen [LIST: {target_dir}] komutuyla yeni projeyi inceleyin.")
    
    return "\n".join(log_buffer)
