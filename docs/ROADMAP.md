# HiveCenter — Yol Haritası (Backlog)

Bu belge, yerel modellerle çalışan otonom ajan sistemini **ürün disipliniyle** büyütmek için fazlı yapılacaklar listesidir. Maddeler issue tracker’a birebir taşınabilir.

**İlkeler**

- Yerel öncelik (cloud yalnızca açık opt-in).
- Varsayılan: en az yetki; geniş dosya erişimi yalnızca allowlist + audit ile.
- İlerleme iddiası: mümkünse test + tool çıktısı + (tercihen) git diff kanıtı.
- Uzun görevler: checkpoint / resume zorunlu (ileride).

---

## Mevcut durum (çekirdek)

- Flask backend (`bin/hive_server.py`), paket `hivecenter/`, `config.json` ile yapılandırma.
- NDJSON stream: `run_id`, `phase`, `iteration`; roller: architect / coder / inspector + `gate` (verify).
- Araçlar (policy + audit): LIST, **STAT**, **GLOB**, READ (tam dosya veya **`#Lstart-Lend` satır aralığı**), CREATE, PATCH (unified diff), MKDIR, SHELL (denylist + isteğe bağlı `approval_triggers` kuyruğu), SEARCH (`rg`), SEMANTIC (Ollama `nomic-embed-text` vb.), GIT (`status` / `diff` / `diff --stat` / **`log -n … --oneline`**).
- Checkpoint: `workspace/.hive/run_<uuid>.json`; audit: `workspace/logs/audit.ndjson`; hafıza: `workspace/memory.json`.
- Müfettiş: `PERFECTION:` + `config.json` içindeki eşik; isteğe bağlı `verify.test_command` veya UI’dan test komutu.
- API: `/api/system` (GPU opsiyonel), `/api/health`, `/api/config`, `/api/memory`, `/api/agent-state` (AGENT_STATE.md kuyruğu), **`GET /api/audit`** (audit.ndjson son kayıtlar), `/api/runs` + `/api/runs/<id>`, `/api/approvals` (+ `approved_ready`, `/resolve`, `/execute`).
- Mimara bağlam: `autonomy.inject_agent_state_tail` ile `AGENT_STATE.md` son baytları plan prompt’una eklenir (P4.2).
- Dashboard: hedef, isteğe bağlı test komutu ve resume UUID, run/phase göstergesi; Fabrika’da **akış zaman çizelgesi**; Sistem sekmesinde **denetim** (audit) özeti; `/api/system` CPU/RAM.
- Test: `python -m unittest tests.test_policy`.

---

## Faz 0 — Güvenlik, politika, denetim

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P0.1 | Tehdit modeli özeti (`docs/THREAT_MODEL.md` ile hizalı) | P0 | Risk senaryoları ve mitigasyon maddeleri yazılı |
| P0.2 | Policy engine: allowlist kökler, yasaklı path örnekleri | P0 | Yazma öncesi kontrol; reddedilen işlem audit’e düşer |
| P0.3 | Audit log şeması: correlation id, ajan, tool, özet sonuç | P0 | Append-only veya rotasyonlu log formatı tanımlı |
| P0.4 | Shell: timeout, max çıktı boyutu, blok listesi komutlar | P0 | Sınır aşımında kontrollü kesilme ve log |
| P0.5 | Path normalizasyonu: `realpath`, symlink politikası | P0 | Kaçak path yazımı engellenir veya onay ister |
| P0.6 | Log redaksiyonu (token/secret sızıntısı) | P1 | Yaygın pattern’ler için maskeleme |
| P0.7 | İnsan onayı kuyruğu (yüksek risk işlemler) | P1 | UI/API’de onay/ret akışı tasarımı + stub |

---

## Faz 1 — Orkestrasyon ve durum makinesi

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P1.1 | Canonical görev JSON şeması: goal, steps, state, artifacts | P0 | Şema dosyası + örnek instance |
| P1.2 | Durum makinesi: queued → planning → executing → verifying → … | P0 | Geçişler tek yerde tanımlı |
| P1.3 | Checkpoint / resume (disk üstünde state) | P0 | Süreç kesilince kaldığı yerden devam |
| P1.4 | Bütçe limitleri: max adım, max süre, stall detection | P1 | Limit aşımında kontrollü fail + rapor |
| P1.5 | Hata sınıflandırması: tool vs model vs policy | P1 | Recovery stratejisi ayrımı |

---

## Faz 2 — Araç platformu (Tooling SDK)

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P2.1 | Tool sözleşmesi: JSON schema, versiyonlama | P0 | Yeni tool eklemek için şablon |
| P2.2 | Filesystem: list/read/write/mkdir (policy gated) | P0 | Unit test + policy test |
| P2.3 | Search: ripgrep wrapper, limit ve exclude | P1 | Büyük repo güvenli tarama |
| P2.4 | Git: status/diff/branch/commit (policy gated) | P1 | Minimum viable git akışı |
| P2.5 | Test runner: komut şablonları + artifact yakalama | P0 | Çıktı özeti state’e bağlanır |

---

## Faz 3 — Kod değişimi disiplini

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P3.1 | Unified diff veya güvenli patch uygulama | P0 | Halüsinasyon yerine izlenebilir değişim |
| P3.2 | UI/API’de diff önizleme (onay modunda) | P1 | Onaysız otomatik yazım politikaya bağlı |
| P3.3 | Çakışma stratejisi ve insan escalasyonu | P2 | Merge çatışması senaryosu tanımlı |

---

## Faz 4 — Bağlam motoru

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P4.1 | Repo haritası / özet üretimi | P1 | Entrypoint ve önemli dosyalar |
| P4.2 | Rolling çalışma notu (`AGENT_STATE.md` vb.) | P1 | Token bütçesi ile uyumlu özet |
| P4.3 | (İsteğe bağlı) yerel embedding indeksi | P2 | Incremental güncelleme planı |

---

## Faz 5 — Kalite kapıları (QA)

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P5.1 | Çok katmanlı gate: statik + test + inspector | P0 | Tek skor yerine birleşik karar kuralı |
| P5.2 | Regression görev seti (küçük, sabit) | P0 | CI veya manuel “release öncesi koş” |
| P5.3 | Hata raporu şablonu (repro + log + diff) | P1 | Debug paketi export |

---

## Faz 6 — Hafıza ve ölçülü self-improvement

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P6.1 | `workspace/memory.json` şeması: fact vs hypothesis | P0 | Çelişki çözüm kuralı yazılı |
| P6.2 | Skill/recipe kütüphanesi (başarılı görevden şablon) | P2 | Versiyonlu kayıt |
| P6.3 | Hafıza sağlığı denetim görevleri | P2 | Periyodik doğrulama |

---

## Faz 7 — Gözlemlenebilirlik

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P7.1 | Structured logging (correlation id, step id) | P1 | Tek görev izi takip edilebilir |
| P7.2 | Metrikler: süre, başarı oranı, kaynak | P2 | Dashboard ile hizalı |
| P7.3 | Debug zip export (log + state + diff) | P2 | Tek pakette teşhis |

---

## Faz 8 — UI/UX

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P8.1 | Görev sihirbazı: hedef + kök + risk + test komutu | P1 | Yeni kullanıcı akışı |
| P8.2 | Timeline: adım ve tool çağrıları | P1 | Kısaltılmış/expand çıktı |
| P8.3 | Onay ekranı (riskli işlemler) | P1 | Policy ile entegre |

---

## Faz 9 — Model stratejisi

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P9.1 | Model kartları (rol başına güçlü/zayıf) | P2 | Dokümante profil |
| P9.2 | Prompt versiyonlama (`prompts/v…`) | P2 | Geri dönüşülebilir değişiklik |
| P9.3 | Eval harness: aynı görev setiyle karşılaştırma | P2 | Regresyonla birleşik |

---

## Faz 10 — Paketleme

| ID | Görev | Öncelik | Teslim (DoD) |
|----|--------|---------|----------------|
| P10.1 | `config.yaml` (kökler, modeller, limitler) | P1 | Tek dosyadan yapılandırma |
| P10.2 | Semver + changelog disiplini | P2 | Sürüm notları şablonu |

---

## Önerilen ilk sprint sırası (özet)

1. P0.2 + P0.3 + P0.4 + P0.5 (policy + audit + shell sınırları + path)
2. P1.1 + P1.2 + P1.3 (şema + state machine + resume)
3. P2.1 + P2.2 + P2.5 (tool SDK + FS + test runner)
4. P5.1 (gate birleştirme) + P5.2 (küçük regression seti)
5. P3.1 (patch disiplini)

---

## Revizyon

| Tarih | Not |
|-------|-----|
| 2026-03-21 | İlk sürüm |
