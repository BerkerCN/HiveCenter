# hivecenter/llm_client.py
import os
import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILE = os.path.expanduser("~/.hivecenter_config.json")


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Çok yüksek num_ctx birçok model/GPU'da KV ayırımı başarısız olur → Ollama HTTP 500.
def _ollama_num_ctx() -> int:
    env = os.environ.get("OLLAMA_NUM_CTX", "").strip()
    if env.isdigit():
        return max(512, min(int(env), 262144))
    try:
        path = os.path.join(_repo_root(), "config.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            n = cfg.get("ollama", {}).get("num_ctx")
            if isinstance(n, int) and n >= 512:
                return n
    except Exception:
        pass
    return 8192


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def _ollama_request_timeout_sec() -> float:
    """Ollama /api/chat HTTP bekleme süresi (deepseek-r1 / büyük num_predict yavaş olabilir)."""
    env = os.environ.get("OLLAMA_REQUEST_TIMEOUT", "").strip()
    if env.replace(".", "").isdigit():
        return max(60.0, float(env))
    try:
        path = os.path.join(_repo_root(), "config.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            t = cfg.get("ollama", {}).get("request_timeout_sec")
            if isinstance(t, (int, float)) and float(t) >= 60:
                return float(t)
    except Exception:
        pass
    return 900.0


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def resolve_openai_api_key() -> str:
    """Dosya (~/.hivecenter_config.json) + OPENAI_API_KEY + HIVECENTER_OPENAI_API_KEY."""
    cfg = load_config()
    return (
        str(cfg.get("openai_api_key") or "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("HIVECENTER_OPENAI_API_KEY", "").strip()
    )


def resolve_anthropic_api_key() -> str:
    """Dosya + ANTHROPIC_API_KEY + HIVECENTER_ANTHROPIC_API_KEY."""
    cfg = load_config()
    return (
        str(cfg.get("anthropic_api_key") or "").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        or os.environ.get("HIVECENTER_ANTHROPIC_API_KEY", "").strip()
    )


def resolve_gemini_api_key() -> str:
    """Dosya + GEMINI_API_KEY + HIVECENTER_GEMINI_API_KEY."""
    cfg = load_config()
    return (
        str(cfg.get("gemini_api_key") or "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("HIVECENTER_GEMINI_API_KEY", "").strip()
    )


def api_key_sources_meta() -> Dict[str, str]:
    """UI: anahtar dosyada mı, ortamda mı (değer döndürmez)."""
    cfg = load_config()
    fo = bool(str(cfg.get("openai_api_key") or "").strip())
    fa = bool(str(cfg.get("anthropic_api_key") or "").strip())
    fg = bool(str(cfg.get("gemini_api_key") or "").strip())
    eo = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("HIVECENTER_OPENAI_API_KEY"))
    ea = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("HIVECENTER_ANTHROPIC_API_KEY"))
    eg = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("HIVECENTER_GEMINI_API_KEY"))
    return {
        "openai_key_source": "file" if fo else ("env" if eo else "none"),
        "anthropic_key_source": "file" if fa else ("env" if ea else "none"),
        "gemini_key_source": "file" if fg else ("env" if eg else "none"),
    }


def _normalize_messages_for_ollama(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for m in messages:
        role = (m.get("role") or "user").strip() or "user"
        content = m.get("content")
        if content is None:
            content = ""
        content = str(content)
        if role == "system" and not content.strip():
            continue
        out.append({"role": role, "content": content})
    if not out:
        out.append({"role": "user", "content": "(no content)"})
    return out


def _parse_ollama_chat_response(result: Dict[str, Any]) -> str:
    msg = result.get("message")
    if isinstance(msg, dict):
        text = msg.get("content") or ""
        if isinstance(text, str) and text.strip():
            return text
        for k in ("thinking", "reasoning_content", "reasoning"):
            t = msg.get(k)
            if isinstance(t, str) and t.strip():
                return t
        return text if isinstance(text, str) else ""
    if isinstance(msg, str):
        return msg
    return ""


def _http_error_body(e: urllib.error.HTTPError) -> str:
    try:
        raw = e.read().decode("utf-8", errors="replace")
        if raw:
            try:
                j = json.loads(raw)
                return str(j.get("error") or j.get("message") or raw)[:600]
            except Exception:
                return raw[:600]
    except Exception:
        pass
    return str(e.reason or "")


def _format_ollama_failure(model: str, e: BaseException, num_ctx_hint: Optional[int] = None) -> str:
    if isinstance(e, urllib.error.HTTPError):
        detail = _http_error_body(e)
        ctx = f", num_ctx={num_ctx_hint}" if num_ctx_hint is not None else ""
        hint = ""
        if e.code == 500:
            hint = (
                " Olası nedenler: VRAM yetersiz (num_ctx düşürün), model bozuk veya Ollama sürümü. "
                "`OLLAMA_NUM_CTX=4096` veya `OLLAMA_NUM_CTX=2048` deneyin; `ollama ps` ile model durumuna bakın."
            )
        return (
            f"[LLM_ROUTER_ERROR] Ollama HTTP {e.code} (model={model}{ctx}). {detail}{hint}"
        )
    if isinstance(e, urllib.error.URLError):
        return (
            f"[LLM_ROUTER_ERROR] Yerel model '{model}' Ollama'ya ulaşılamıyor: {e}. "
            f"OLLAMA_HOST={_ollama_base_url()} — Ollama çalışıyor mu? (`curl {_ollama_base_url()}/api/tags`)"
        )
    msg = str(e).lower()
    if "timed out" in msg or "timeout" in msg:
        return (
            f"[LLM_ROUTER_ERROR] Ollama: {e} "
            f"(İstek süresi aşıldı; config.json ollama.request_timeout_sec artırın veya OLLAMA_REQUEST_TIMEOUT=1200, "
            f"OLLAMA_NUM_CTX düşürün, `ollama ps` ile model yükünü kontrol edin.)"
        )
    return f"[LLM_ROUTER_ERROR] Ollama: {e}"


def _ollama_chat_request(
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    url = f"{base_url}/api/chat"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if options:
        payload["options"] = options
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    to = float(timeout_sec) if timeout_sec is not None else _ollama_request_timeout_sec()
    with urllib.request.urlopen(req, timeout=to) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_timeout_exc(e: BaseException) -> bool:
    if isinstance(e, TimeoutError):
        return True
    s = str(e).lower()
    return "timed out" in s or "timeout" in s


def _ollama_chat_request_resilient(
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
    timeout_sec: float,
) -> Dict[str, Any]:
    """Aynı isteği zaman aşımında bir kez daha dene (yavaş GPU / ilk yükleme)."""
    try:
        return _ollama_chat_request(base_url, model, messages, options, timeout_sec=timeout_sec)
    except Exception as e:
        if _is_timeout_exc(e):
            return _ollama_chat_request(base_url, model, messages, options, timeout_sec=timeout_sec)
        raise


_OLLAMA_MERGE_KEYS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "num_ctx",
        "num_batch",
        "num_gpu",
        "main_gpu",
        "num_thread",
        "num_predict",
        "repeat_penalty",
        "repeat_last_n",
    }
)


def _ollama_role_options_from_config(role: Optional[str]) -> Dict[str, Any]:
    """config.json içindeki ollama + ollama.<role> birleşimi (chat options)."""
    if not role:
        return {}
    try:
        path = os.path.join(_repo_root(), "config.json")
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        o = cfg.get("ollama")
        if not isinstance(o, dict):
            return {}
        merged: Dict[str, Any] = {}
        for k, v in o.items():
            if k in _OLLAMA_MERGE_KEYS and v is not None:
                merged[k] = v
        sub = o.get(role)
        if isinstance(sub, dict):
            for k, v in sub.items():
                if k in _OLLAMA_MERGE_KEYS and v is not None:
                    merged[k] = v
        return merged
    except Exception:
        return {}


def _ollama_retry_option_sets(
    temperature: float,
    base_ctx: int,
    role_opts: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, Dict[str, Any]]]:
    """(label, options) — sırayla dene; role_opts config'ten (num_batch, num_thread, …)."""
    ro = {k: v for k, v in (role_opts or {}).items() if k in _OLLAMA_MERGE_KEYS and v is not None}
    if "temperature" not in ro:
        ro["temperature"] = temperature
    ctx_primary = int(ro.get("num_ctx", base_ctx) or base_ctx)
    ctx_primary = max(512, min(ctx_primary, 262144))
    ro_with_ctx = {**ro, "num_ctx": ctx_primary}

    out: List[Tuple[str, Dict[str, Any]]] = [
        ("config_num_ctx", ro_with_ctx),
    ]
    ro_no_ctx = {k: v for k, v in ro.items() if k != "num_ctx"}
    out.append(("no_num_ctx", ro_no_ctx))
    for ctx in (4096, 2048, 1024):
        if ctx < ctx_primary:
            out.append((f"num_ctx_{ctx}", {**ro, "num_ctx": ctx}))
    return out


def call_ollama_role(role: str, model: str, prompt: str, system: str = "") -> str:
    """Swarm / test yardımcıları için: tek Ollama sohbet çağrısı."""
    if not (model or "").strip():
        return "ERROR: no model configured for role"
    return chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        model=model.strip(),
        temperature=0.7 if role == "coder" else 0.2,
        max_tokens=4000,
        ollama_role=role if role in ("architect", "coder", "inspector") else None,
    )


def _sliding_window_memory(messages: List[Dict[str, str]], max_msgs=25) -> List[Dict[str, str]]:
    """V5.0 AGI Upgrade: Prevents context bloat in 30+ iter tasks."""
    if len(messages) <= max_msgs:
        return messages
    
    head = messages[:3]
    tail = messages[-10:]
    omitted = len(messages) - len(head) - len(tail)
    
    warning = f"\\n\\n[SYSTEM ALERT: {omitted} turns of older history were automatically compressed to free up RAM. Continue!/]\\n\\n"
    new_tail = []
    for i, m in enumerate(tail):
        if i == 0:
            new_tail.append({"role": m["role"], "content": warning + str(m.get("content", ""))})
        else:
            new_tail.append(m)
    return head + new_tail


def chat_completion(
    messages: List[Dict[str, str]],
    model: str = "llama3.1:8b",
    temperature: float = 0.2,
    base_url: str = "http://127.0.0.1:11434",
    max_tokens: int = 4096,
    ollama_role: Optional[str] = None,
) -> str:
    del max_tokens  # Ollama /api/chat bazı sürümlerde ayrı parametre; şimdilik kullanılmıyor
    model = (model or "").strip()
    if not model:
        return "[LLM_ROUTER_ERROR] Model adı boş. Ayarlar & API'de rol başına model seçin."
    messages = _sliding_window_memory(messages, 25)

    try:
        from hivecenter.oracle import get_oracle_insights
        oracle_data = get_oracle_insights()
        if oracle_data:
            messages.insert(0, {"role": "system", "content": oracle_data})
    except Exception:
        pass

    if model.startswith("gemini"):
        api_key = resolve_gemini_api_key()
        if not api_key:
            return (
                "[LLM_ROUTER_ERROR] Gemini modeli seçildi ancak API anahtarı yok. "
                "Ayarlar'dan gemini_api_key girin veya GEMINI_API_KEY / HIVECENTER_GEMINI_API_KEY ortam değişkenini ayarlayın."
            )
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        contents = []
        system_instruction = ""
        for m in messages:
            if m["role"] == "system":
                system_instruction += m["content"] + "\n\n"
            else:
                r = "user" if m["role"] == "user" else "model"
                contents.append({"role": r, "parts": [{"text": m["content"]}]})
                
        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_instruction.strip()}]
            },
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192
            }
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                resp_json = json.loads(response.read().decode("utf-8"))
                try:
                    return resp_json["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    return f"[LLM_ROUTER_ERROR] Gemini response format unexpected: {resp_json}"
        except urllib.error.HTTPError as e:
            try:
                err_b = e.read()
                return f"[LLM_ROUTER_ERROR] Gemini HTTP API hatası: {e} - {err_b.decode('utf-8')}"
            except:
                return f"[LLM_ROUTER_ERROR] Gemini HTTP API hatası: {e}"
        except Exception as e:
            return f"[LLM_ROUTER_ERROR] Gemini API isteği başarısız oldu: {e}"

    if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
        api_key = resolve_openai_api_key()
        if not api_key:
            return (
                "[LLM_ROUTER_ERROR] OpenAI modeli seçildi ancak API anahtarı yok. "
                "Ayarlar'dan openai_api_key girin veya OPENAI_API_KEY / HIVECENTER_OPENAI_API_KEY ortam değişkenini ayarlayın."
            )
        import openai

        cli = openai.OpenAI(api_key=api_key)
        resp = cli.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""

    if model.startswith("claude-"):
        api_key = resolve_anthropic_api_key()
        if not api_key:
            return (
                "[LLM_ROUTER_ERROR] Anthropic model seçildi ancak API anahtarı yok. "
                "Ayarlar'dan anthropic_api_key girin veya ANTHROPIC_API_KEY / HIVECENTER_ANTHROPIC_API_KEY ortam değişkenini ayarlayın."
            )
        import anthropic

        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg += m["content"] + "\n"
            else:
                user_msgs.append(m)
        cli = anthropic.Anthropic(api_key=api_key)
        resp = cli.messages.create(
            model=model,
            system=system_msg.strip(),
            messages=user_msgs,
            temperature=temperature,
            max_tokens=4096,
        )
        return resp.content[0].text

    # Ollama
    bu = (base_url or _ollama_base_url()).rstrip("/")
    if bu == "http://localhost:11434":
        bu = _ollama_base_url()

    norm = _normalize_messages_for_ollama(messages)
    base_ctx = _ollama_num_ctx()
    role_opts = _ollama_role_options_from_config(ollama_role)
    if role_opts.get("temperature") is not None:
        try:
            temperature = float(role_opts["temperature"])
        except (TypeError, ValueError):
            pass
    last_exc: Optional[BaseException] = None
    last_label = ""
    last_opts: Optional[Dict[str, Any]] = None

    req_timeout = _ollama_request_timeout_sec()
    for label, opts in _ollama_retry_option_sets(temperature, base_ctx, role_opts):
        last_label = label
        last_opts = opts
        try:
            result = _ollama_chat_request_resilient(bu, model, norm, opts, req_timeout)
            text = _parse_ollama_chat_response(result)
            if text or result.get("done") is not None:
                return text
            return ""
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code in (500, 502, 503) and label != "num_ctx_1024":
                try:
                    e.read()
                except Exception:
                    pass
                continue
            return _format_ollama_failure(model, e, opts.get("num_ctx"))
        except urllib.error.URLError as e:
            last_exc = e
            break
        except Exception as e:
            last_exc = e
            break

    if last_exc is not None:
        nctx = last_opts.get("num_ctx") if last_opts else None
        return _format_ollama_failure(model, last_exc, nctx)
    return "[LLM_ROUTER_ERROR] Ollama: bilinmeyen durum."
