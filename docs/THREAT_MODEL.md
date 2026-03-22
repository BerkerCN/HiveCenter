# HiveCenter — Tehdit Modeli (Taslak)

Bu belge, otonom ajanın dosya sistemi ve shell erişimi büyüdükçe ortaya çıkabilecek riskleri **erken** tanımlar ve mitigasyon yönünü netleştirir. Ürün kararları (policy, onay, audit) buraya referans vermelidir.

**Kapsam**: Yerel çalışan backend (`hive_server`), workspace ve (gelecekte) genişletilmiş kök dizinler; yerel Ollama çağrıları.

**Varsayılan güvenlik pozisyonu**: En az yetki; yazma işlemleri allowlist içinde; şüpheli işlemler onay veya reddedilme.

---

## 1) Varlıklar (korunması gerekenler)

| Varlık | Açıklama | Önem |
|--------|-----------|------|
| Kullanıcı verisi | Projeler, kişisel dosyalar | Yüksek |
| Kimlik bilgileri | SSH anahtarları, tokenlar, `.env` | Kritik |
| Sistem bütünlüğü | `/etc`, servisler, paket yöneticisi | Kritik |
| İtibar / güven | Yanlışlıkla yayınlanan sır veya kod | Orta–Yüksek |
| Erişilebilirlik | Ajanın disk/doluluk ile sistemi kilitlemesi | Orta |

---

## 2) Tehdit aktörleri

| Aktör | Amaç | Not |
|--------|------|-----|
| Kötü niyetli kullanıcı girdisi | Zararlı talimat (prompt injection tarzı) | Model araçları tetikler |
| Hatalı model çıktışı | Yanlış path veya tehlikeli komut | En sık gerçek dünya riski |
| Üçüncü taraf içerik | Okunan dosyada gizli talimat | Repo içi README vb. |
| Paylaşılan makine | Başka süreç / kullanıcı | İleride çok kullanıcılı senaryo |

---

## 3) Saldırı yüzeyleri (attack surface)

| Yüzey | Örnek | Risk |
|--------|--------|------|
| `[SHELL: …]` | `rm -rf`, `curl | sh`, fork bomb | Kritik |
| `[CREATE: path]` / yazım | Hassas dizinlere dosya | Yüksek |
| `[READ: …]` | SSH private key okuma | Yüksek (gizlilik) |
| Path traversal | `../` ile allowlist dışına çıkma | Yüksek |
| Symlink | Allowlist içinden hedef dışına link | Yüksek |
| Kaynak tüketimi | Çok büyük çıktı, uzun süre | Orta (DoS) |
| Log sızıntısı | Secret’ların loga yazılması | Yüksek |

---

## 4) Tehdit senaryoları (STRIDE tarzı özet)

### Spoofing / Yanıltma

- Model “başarılı” der; test çalışmamıştır.  
  **Mitigasyon**: Test gate, komut çıktısı zorunluluğu, şüpheli iddialarda yeniden çalıştırma.

### Tampering / Manipülasyon

- Araç çağrısı araya girer veya dosya yarış durumu.  
  **Mitigasyon**: Atomik yazma (tmp + rename), işlem sırası tek thread veya kilit (ileride).

### Repudiation / İnkar

- “Ne oldu bilinmiyor.”  
  **Mitigasyon**: Audit log + correlation id + export paketi.

### Information disclosure

- `.env`, `id_rsa`, tarayıcı cookie dosyaları okunması.  
  **Mitigasyon**: Okuma politikası, varsayılan deny, hassas path listesi.

### Denial of service

- Aşırı shell, disk doldurma, CPU spike.  
  **Mitigasyon**: Timeout, çıktı limiti, disk kotası (ileride), adım bütçesi.

### Elevation of privilege

- Normal kullanıcıdan root’a sıçrama (sudo).  
  **Mitigasyon**: Sudo/su blok listesi veya onay; düşük ayrıcalıklı çalışma (ileride).

---

## 5) Politika maddeleri (uygulanacak kurallar — taslak)

1. **Allowlist kökleri**: Yazma yalnızca açıkça tanımlı kökler altında (ör. `workspace/`, kullanıcı onaylı `~/Projeler/...`).
2. **Yasaklı path kalıpları**: Örn. `~/.ssh`, `/etc`, `/root` (ürün kararıyla genişletilir/daraltılır).
3. **Normalizasyon**: Tüm path’ler normalize edilir; symlink hedefi kontrol edilir (politika: takip et / reddet).
4. **Shell allowlist/denylist**: Üretimde en azından denylist (ör. `rm -rf /`, `mkfs`, `dd of=/dev/...`).
5. **Çıktı ve süre sınırı**: Komut çıktısı üst sınırı; aşımda kes ve logla.
6. **Audit**: Her tool çağrısı kayda geçer (özet + sonuç kodu).
7. **İnsan onayı**: Policy ihlali değil ama yüksek riskli işlemler kuyrukta onay bekler.

---

## 6) Açık riskler (bilerek kabul / sonraki iterasyon)

- **Tek kullanıcı varsayımı**: Çok kullanıcılı izolasyon yok.
- **Tam sandbox (container/VM)**: Henüz zorunlu değil; ileride önerilir.
- **Model güvenilirliği**: Tamamen yerel olsa da halüsinasyon riski kalır; tek çözüm kanıt kapılarıdır.

---

## 7.1) Onaylı komut çalıştırma (`/api/approvals/<id>/execute`)

- Yalnızca `status=approved` ve henüz `executed_at` olmayan kayıtlar çalıştırılır.
- **hard_deny** (`shell_safe` + `config.shell.hard_deny_substrings`) onaylı bile olsa engellenir (`rm -rf /`, `mkfs`, vb.).
- Çıktı audit ve kayıtta özetlenir; uzun süre `execute_approved_timeout_sec` ile sınırlıdır.

## 7) Test / doğrulama (tehditlere karşı)

| Test | Beklenti |
|------|----------|
| `../` ile allowlist dışı yazma denemesi | Red + audit |
| Symlink ile kaçak hedef | Red veya politikaya göre |
| Yasaklı komut | Red veya onay kuyruğu |
| Dev secret içeren dosya okuma | Redaksiyon veya deny |

---

## Revizyon

| Tarih | Not |
|-------|-----|
| 2026-03-21 | İlk taslak |
