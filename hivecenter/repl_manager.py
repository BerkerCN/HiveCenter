"""HiveCenter REPL Manager: Veri bilimi ve kalıcı çalışan (stateful) Python ortamı."""
import io
import contextlib
import traceback

# Tüm REPL çağrıları bu global sözlükte yaşar, session kapanana kadar silinmez.
_repl_globals = {}
_repl_locals = {}

def execute_repl(code: str) -> str:
    """Verilen Python kodunu kalıcı bellekte çalıştırır ve stdout çıktısını / hatalarını yakalar."""
    # Sadece print yerine, tek bir ifadenin sonucunu otomatik yazdırmak için 
    # (Jupyter mantığı). Ancak güvenlik ve karışıklık olmaması için try/except kullanır.
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            try:
                val = eval(code, _repl_globals, _repl_locals)
                if val is not None:
                    print(repr(val))
            except SyntaxError:
                exec(code, _repl_globals, _repl_locals)
        except Exception:
            traceback.print_exc()
            
    res = output.getvalue()
    if not res.strip():
        return "(İşlem başarılı, REPL çıktısı yok)"
    return res
