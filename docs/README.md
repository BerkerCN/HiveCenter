# HiveCenter documentation

Engineer-oriented index for this repository. (Turkish column headers below are kept for existing readers.)

| Belge | İçerik |
|--------|--------|
| [ROADMAP.md](./ROADMAP.md) | Fazlı yapılacaklar listesi, öncelikler, Definition of Done |
| [THREAT_MODEL.md](./THREAT_MODEL.md) | Tehdit modeli taslağı ve mitigasyon yönleri |
| [schemas/task_state.v1.json](./schemas/task_state.v1.json) | Checkpoint JSON şeması (taslak) |

Ana uygulama: `bin/hive_server.py`, paket: `hivecenter/`, yapılandırma: `config.json`, arayüz: `dashboard/index.html`, çalışma alanı: `workspace/`.

**Sağlık:** `GET /api/system` (CPU/RAM + isteğe bağlı GPU `nvidia-smi`), `GET /api/health` (+ Ollama erişilebilirlik).

**Otonomi / kalite:** `hivecenter/prompts.py` (Mimar / Kodcu / Müfettiş sistem mesajları), `hivecenter/model_io.py` (Ollama `options`, `strip_reasoning_tags`, gözlem kısaltma), `workspace/AGENT_STATE.md` (iterasyon günlüğü). Müfettiş geri bildirimi sonraki mimar turuna enjekte edilir; `autonomy.inject_agent_state_tail` açıkken AGENT_STATE kuyruğu da Mimara eklenir.

**Uygulanan (özet):** `config.json`; policy + allowlist; audit NDJSON (`workspace/logs/audit.ndjson`); araçlar: LIST/**STAT**/**GLOB**/READ (satır aralığı `#Lstart-Lend`)/CREATE/**PATCH**/MKDIR/SHELL/**SEMANTIC**/SEARCH/GIT (salt okunur `log`; regex’lerde boşluk toleransı); onay kuyruğu + **POST `/api/approvals/<id>/execute`** (onaylı shell, `hard_deny` + timeout); checkpoint `workspace/.hive/run_<uuid>.json`; `/api/config`, `/api/memory`, **`GET /api/agent-state`**, **`GET /api/audit`**, `/api/runs` + `/api/runs/<id>`; doğrulama komutu; testler: `tests/test_policy.py`, `tests/test_patch_apply.py`, `tests/test_shell_safe.py`, `tests/test_prompts.py`, `tests/test_audit_read.py`, `tests/test_tools_capabilities.py`.
