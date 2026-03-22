# HiveCenter — “Siber Kovan Operasyon Merkezi” UI Master Prompt

Aşağıdaki metni bir görsel/ön yüz modeline veya tasarımcıya **tek parça brief** olarak verebilirsin. Amaç: sektör standardının üzerinde, 2026+ hissi veren, **premium otomobil (Ferrari)** seviyesinde cilalı bir arayüz.

---

## Rol ve ton

Sen dünya çapında bir **digital product + motion + HUD** tasarımcısısın. HiveCenter, yerelde çalışan **çok ajanlı yapay zekâ fabrikası**dır. Arayüz “admin paneli” değil; **canlı bir operasyon merkezi / siber kovan** olmalı. Duygu: güç, hassasiyet, teknolojik lüks, tehdit değil — **kontrol**.

## Tasarım ilkesi (zorunlu)

1. **Derinlik katmanları:** Arka plan statik düz renk olamaz; çok hafif **mesh / aurora**, **ince grid veya nöral ağ dokusu**, **film grain**, isteğe bağlı **scanline** — hepsi düşük opaklıkta, okunabilirliği öldürmeden.
2. **Işık dili:** Neon abartısı yok; **kontrollü emisyon** — kenar ışıması (rim light), iç highlight, cam yüzeyde **inner glow**. Pembe / camgöbeği / turuncu **sekonder vurgular**; birincil vurgu **mint–iris** ekseni.
3. **Tipografi:** Display font (Syne, Clash, benzeri) + geometrik sans (Outfit, Geist, benzeri) + teknik işler için mono. Başlıklarda **geniş letter-spacing**, gövdede ferah satır aralığı.
4. **Bileşen dili:** Kartlar **frosted glass** (blur + saturate), **1px** ince border, büyük radius; hover’da **border luminance** artışı, mikro ölçek (scale 1.01).
5. **Veri görünürlüğü:** Ham sayı yığını yerine **mini halka göstergeler**, ince progress, durum için **renk kodlu canlılık** (yeşil–sarı–kırmızı anlamında gradient, literal trafik lambası değil).
6. **Hareket:** Arka planda **yavaş** (20–40s) gradient kayması; UI’de **stagger** yok, sadece **odak ve CTA** için kısa easing. **CTA** tek güçlü pulse / neon halka — sayfa geri kalanı sakin.
7. **İkonografi:** Emoji yok; her nav ve ajan rolü için **özel stroke-tabanlı SVG** (radar, kilit/kalkan, grafik, bellek düğümü, dişli).
8. **Boş durumlar:** “Henüz veri yok” yerine **canlı bekleyen hat** hissi — ince animasyonlu placeholder çizgileri, “CANLI AKIŞ / BEKLEMEDE” etiketi.

## Teknik kısıt

- Tek HTML dosyası + Tailwind CDN + React UMD kabul edilebilir.
- Performans: blur katman sayısı sınırlı; animasyonlar **GPU-dostu** (transform, opacity).
- Erişilebilirlik: kontrast, focus ring, `prefers-reduced-motion` için sakin mod.

## Çıktı beklentisi

Full-screen layout: **sol sabit navigasyon** (ikon + etiket), **orta geniş gövde**, **alt sağ minimal footer**. Fabrika görünümünde **üç ajan sütunu**, altında **görev / şablon / kovan başlat** bölümü. “Kovanı Başlat” görsel olarak **fokal nokta** — neon cam düğme, hover’da ışık süpürme.

---

*Bu dosya HiveCenter deposu için referans brief olarak tutulur; dashboard uygulaması bu yönde evrilir.*
