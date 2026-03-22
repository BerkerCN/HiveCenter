import os
import subprocess
import tempfile
import threading
from gtts import gTTS

def speak_text(text: str, lang: str = "tr"):
    """
    Sentezlenen sesi arkaplanda (asenkron) olarak çalar.
    Sistemi bloklamaz.
    """
    def _play_audio():
        try:
            tts = gTTS(text=text, lang=lang)
            # Geçici bir MP3 dosyası oluştur
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            tts.save(path)
            
            # ffplay yüklü ise oynat, yoksa sessizce sil (veya aplay dene)
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Temizlik
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"TTS Oynatma hatası: {e}")

    # Sesin sistemin geri kalanını bloklamaması için Thread kullanıyoruz.
    threading.Thread(target=_play_audio, daemon=True).start()
    return f"SPOKEN (Arkaplanda çalınıyor): '{text}'"
