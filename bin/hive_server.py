import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from flask import Flask, request, jsonify, Response, send_from_directory

from flask_cors import CORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hivecenter.audit import AuditLogger
from hivecenter.audit_read import read_recent_audit_entries
from hivecenter.config import load_config
from hivecenter.gates import run_verify_command
from hivecenter.memory_store import append_entry, read_memory
from hivecenter.policy import PolicyContext
from hivecenter.repo_map import generate_repo_map
from hivecenter.approvals_store import (
    add_manual_request,
    get_record,
    list_all,
    list_approved_ready,
    list_pending,
    mark_executed,
    resolve as approval_resolve,
)
from hivecenter.agent_state import append_iteration as append_agent_state_log, read_tail as read_agent_state_tail
from hivecenter.health_gpu import get_gpu_metrics
from hivecenter.model_io import (
    observation_has_failures,
    strip_reasoning_tags,
    truncate_observation,
)
from hivecenter.pty_manager import GLOBAL_PTY, PtyManager
from hivecenter.tools import HIVE_ASK_USER_OBS_SEPARATOR, ToolContext, execute_agent_tools
from hivecenter.prompts import (
    ARCHITECT_SYSTEM,
    CODER_SYSTEM,
    INSPECTOR_SYSTEM,
    architect_user_prompt,
    coder_user_prompt,
    inspector_user_prompt,
    build_tools_block,
    build_agent_guide_full
)
from hivecenter.llm_client import (
    api_key_sources_meta,
    chat_completion,
    load_config as load_llm_config,
)

app = Flask(__name__)

# --- V11.0: Persistent Memory & Native OS Picker ---

WORKSPACES_FILE = os.path.expanduser("~/.hivecenter_workspaces.json")

def load_saved_workspaces():
    if os.path.exists(WORKSPACES_FILE):
        try:
            with open(WORKSPACES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_workspace(path):
    ws = load_saved_workspaces()
    if path not in ws:
        ws.insert(0, path)
        with open(WORKSPACES_FILE, 'w') as f:
            json.dump(ws, f)

@app.route("/api/pick_folder", methods=["GET"])
def api_pick_folder():
    """V11.1: Robust Linux Native GUI Folder Picker (Zenity/kdialog/Tkinter)"""
    import subprocess
    import sys
    folder_path = ""
    try:
        # Try Zenity first (standard on GNOME/most Linux)
        if sys.platform.startswith('linux'):
            try:
                folder_path = subprocess.check_output(
                    ['zenity', '--file-selection', '--directory', '--title=HiveCenter: Select workspace folder'],
                    stderr=subprocess.DEVNULL
                ).decode('utf-8').strip()
            except Exception:
                # Fallback to kdialog (KDE)
                try:
                    folder_path = subprocess.check_output(
                        ['kdialog', '--getexistingdirectory', '/'],
                        stderr=subprocess.DEVNULL
                    ).decode('utf-8').strip()
                except Exception:
                    pass

        # If Linux native commands failed or we're on Windows/Mac, fallback to Tkinter
        if not folder_path:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder_path = filedialog.askdirectory(title="HiveCenter: Select workspace folder")
            root.destroy()
            
        if folder_path:
            save_workspace(folder_path)
            return jsonify({"success": True, "path": folder_path})
        return jsonify({"success": False, "error": "Folder selection was cancelled or the native picker could not be started."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/workspaces", methods=["GET"])
def api_get_workspaces():
    ws = load_saved_workspaces()
    return jsonify({"success": True, "workspaces": ws})
# ----------------------------------------------------
CORS(app)

from hivecenter.shell_safe import is_hard_denied
from hivecenter import __version__ as HIVECENTER_VERSION
from hivecenter.state import list_recent_runs, load_run, new_run_id, save_run

CFG = load_config(ROOT)
BASE_WORKSPACE = CFG["workspace_root"]
os.makedirs(BASE_WORKSPACE, exist_ok=True)

MODELS = CFG.get("models", {})
# config yokken veya eksik anahtarda kullanılacak varsayılanlar (coder: daha güçlü kod modeli)
ROLE_FALLBACK_MODEL = {
    "architect": "deepseek-r1:8b",
    "coder": "qwen2.5-coder:14b",
    "inspector": "deepseek-r1:8b",
}


PERFECTION_PRIMARY = re.compile(
    r"(?:^|\n)\s*\*?\*?PERFECTION\*?\*?\s*:\s*(\d{1,3})\b",
    re.IGNORECASE | re.MULTILINE,
)
PERFECTION_FALLBACK = re.compile(
    r"(?:SCORE|PUAN)\s*[:=]\s*(\d{1,3})\b",
    re.IGNORECASE,
)


def reload_config():
    global CFG, BASE_WORKSPACE
    CFG = load_config(ROOT)
    BASE_WORKSPACE = CFG["workspace_root"]
    os.makedirs(BASE_WORKSPACE, exist_ok=True)
    MODELS.update(CFG.get("models", {}))


def get_system_metrics():
    cpu_pct = 0.0
    mem_pct = 0.0
    try:
        n = os.cpu_count() or 1
        load1, _, _ = os.getloadavg()
        cpu_pct = min(100.0, round(100.0 * (load1 / max(n, 1)), 1))
    except (OSError, AttributeError):
        cpu_pct = 0.0
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = {}
            for _ in range(48):
                line = f.readline()
                if not line:
                    break
                parts = line.split()
                if len(parts) >= 2 and parts[0].endswith(":"):
                    key = parts[0].rstrip(":")
                    info[key] = int(parts[1])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        if total > 0:
            mem_pct = round(100.0 * (1.0 - (avail / total)), 1)
    except (OSError, ValueError, ZeroDivisionError):
        mem_pct = 0.0
    out = {"cpu_percent": cpu_pct, "memory_percent": mem_pct}
    gpu = get_gpu_metrics()
    if gpu:
        out["gpu"] = gpu
    return out


def ollama_health_metrics():
    """Tek istek: Ollama erişilebilirliği, gecikme (ms), yerel model sayısı."""
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as res:
            raw = res.read().decode()
            ms = (time.perf_counter() - t0) * 1000
            data = json.loads(raw)
            n = len(data.get("models") or [])
            return True, round(ms, 1), n
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        return False, round(ms, 1), 0


def extract_perfection_score(text: str) -> int:
    if not text or not text.strip():
        return 0
    m = PERFECTION_PRIMARY.search(text)
    if m:
        return max(0, min(100, int(m.group(1))))
    m = PERFECTION_FALLBACK.search(text)
    if m:
        return max(0, min(100, int(m.group(1))))
    m = re.search(r"\b(\d{1,3})\s*/\s*100\b", text)
    if m:
        return max(0, min(100, int(m.group(1))))
    return 0


def _coder_claimed_done(coding_res: str) -> bool:
    """Sadece kodcu çıktısındaki [DONE] / [DONE: ...] kapanışı sayılır (müfettişteki [DONE] run'ı bitirmesin)."""
    return bool(re.search(r"\[\s*DONE\b", coding_res or "", re.IGNORECASE))


def _coder_did_real_work(coding_res: str) -> bool:
    """CREATE/REPLACE/SHELL/PATCH — sadece SET_TEST_CMD / REPLY ile geçilen tur yetersiz sayılır."""
    if not coding_res:
        return False
    return bool(
        re.search(
            r"\[\s*(?:CREATE|REPLACE|SHELL|PATCH|MKDIR)\s*:",
            coding_res,
            re.IGNORECASE,
        )
    )


def _strip_cfg(text: str) -> str:
    return strip_reasoning_tags(text, CFG.get("ollama", {}).get("strip_reasoning_tags", True))


def _make_tool_ctx(run_id: str, user_goal: str = "") -> ToolContext:
    sh = CFG.get("shell", {})
    sem = CFG.get("semantic", {})
    return ToolContext(
        workspace_root=BASE_WORKSPACE,
        policy=PolicyContext(CFG),
        audit=AuditLogger(CFG["_audit_log_abs"], CFG.get("audit", {}).get("redact", True)),
        correlation_id=run_id,
        shell_timeout=int(sh.get("timeout_sec", 15)),
        shell_max_out=int(sh.get("max_output_bytes", 262144)),
        shell_deny=list(sh.get("deny_substrings", [])),
        read_max_bytes=int(CFG.get("read_max_bytes", 512000)),
        search_cfg=CFG.get("search", {}),
        glob_cfg=CFG.get("glob", {}),
        patch_cfg=CFG.get("patch", {}),
        semantic_cfg=sem,
        embed_model=str(sem.get("embed_model", "nomic-embed-text")),
        approval_triggers=list(sh.get("approval_triggers", [])),
        cursor_master=CFG.get("cursor_master", {}) if isinstance(CFG.get("cursor_master"), dict) else {},
        user_goal=user_goal or "",
    )


@app.route("/start", methods=["POST"])
def start_hive():
    reload_config()
    data = request.json or {}
    goal = (data.get("goal") or "").strip()
    resume_id = (data.get("resume_run_id") or "").strip()
    
    # V12.0 Auto-Prompt Enhancer (Prompt Zenginleştirici)
    if goal and not resume_id and len(goal) < 150:
        try:
            from hivecenter.llm_client import call_ollama_role
            from hivecenter.prompts import ENHANCER_SYSTEM
            enc_model = CFG.get("architect_model", "qwen2.5-coder:7b")
            enhanced = call_ollama_role("architect", enc_model, goal, ENHANCER_SYSTEM)
            if enhanced and len(enhanced) > 15:
                # Orijinal kullanıcı hedefini not düşerek asıl goal'ı detaylı plana çevir
                goal = enhanced.strip() + f"\n\n[Orijinal Kullanıcı İsteği: {goal}]"
        except Exception as e:
            print("Enhancer error:", e)

    # V7.0 God-Mode: Trigger Oracle API Daemon
    if goal:
        try:
            from hivecenter.oracle import trigger_oracle_daemon
            trigger_oracle_daemon(goal)
        except Exception:
            pass
            
    test_override = data.get("test_command")
    if not goal and not resume_id:
        return jsonify({"error": "goal or resume_run_id required"}), 400

    verify_cfg = CFG.get("verify", {})
    test_cmd = test_override if test_override is not None else verify_cfg.get("test_command")
    require_test = bool(verify_cfg.get("require_pass_for_done", False))

    # V15: Dynamic Quotas
    is_large_app = any(kw in goal.lower() for kw in ["app", "uygulama", "react", "vue", "nextjs", "web", "site", "fullstack", "full-stack", "proje", "oyun"])
    max_iter = int(CFG.get("run", {}).get("max_iterations", 25 if is_large_app else 5))
    threshold = int(CFG.get("run", {}).get("perfection_threshold", 72))

    def generate():
        nonlocal goal, test_cmd
        reload_config()
        
        proj_folder = str(data.get("project_folder") or "").strip()
        if proj_folder:
            # V11.0 Native Support: Check if the provided path is an absolute path (via Tkinter Native Picker)
            if os.path.isabs(proj_folder):
                project_path = proj_folder
                save_workspace(project_path)
            else:
                project_path = os.path.join(BASE_WORKSPACE, proj_folder)
            os.makedirs(project_path, exist_ok=True)
            
            # V13.0 Otonom Sandbox Isolation: Set ENV so all modules (RAG, Graph) use this folder!
            os.environ["HIVECENTER_PROJECT_PATH"] = project_path
        else:
            project_path = BASE_WORKSPACE
            os.environ["HIVECENTER_PROJECT_PATH"] = project_path
            
        # V8.0 God-Mode: Activate the Auto-Immune Daemon (if not already running)
        try:
            if not getattr(app, "immune_active", False):
                from hivecenter.immune_system import activate_immune_system
                activate_immune_system(project_path)
                app.immune_active = True
        except Exception:
            pass
            
        policy = PolicyContext(CFG)
        _, werr = policy.path_allowed(project_path)
        if werr:
            yield json.dumps({"phase": "failed", "agent": "system", "status": "Policy", "content": werr}) + "\n"
            return

        if resume_id:
            st = load_run(project_path, resume_id)
            if not st:
                yield json.dumps(
                    {"phase": "failed", "agent": "system", "status": "Error", "content": f"run not found: {resume_id}"}
                ) + "\n"
                return
            run_id = resume_id
            
            # V13: Append User Reply to Goal if provided
            old_goal = st.get("goal") or ""
            if goal and goal != old_goal:
                goal = old_goal + f"\n\n[USER INSTRUCTION / REPLY]: {goal}"
                current_context = st.get("current_context", "") + f"\n\n[USER REPLY]: {goal}"
            else:
                goal = old_goal
                current_context = st.get("current_context") or "Project initialized."
                
            iteration = int(st.get("iteration", 1))
            consecutive_failures = int(st.get("consecutive_failures", 0))
            if test_cmd is None:
                test_cmd = st.get("test_command")
        else:
            run_id = new_run_id()
            iteration = 1
            current_context = "Project initialized."
            consecutive_failures = 0

        last_feedback = None
        last_score = None
        if resume_id:
            last_feedback = st.get("last_inspector_feedback")
            last_score = st.get("last_perfection")

        save_run(
            project_path,
            run_id,
            {
                "goal": goal,
                "test_command": test_cmd,
                "iteration": iteration,
                "phase": "queued",
                "current_context": current_context,
            },
        )

        tool_ctx = _make_tool_ctx(run_id, goal)
        tool_ctx.workspace_root = project_path
        if is_large_app:
            # npm install / first-time builds often exceed 60s; avoid timeout loops.
            tool_ctx.shell_timeout = max(tool_ctx.shell_timeout, 300)
            tool_ctx.shell_max_out = max(tool_ctx.shell_max_out, 500000)
            
        tools_block = build_tools_block()
        agent_guide_full = build_agent_guide_full(goal, tools_block)
        max_obs = int(CFG.get("autonomy", {}).get("max_observation_chars", 16000))

        # Load dynamic agent models from ~/.hivecenter_config.json
        llm_cfg = load_llm_config()

        def _effective_model(key: str, role: str) -> str:
            v = llm_cfg.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            m = MODELS.get(role) if isinstance(MODELS, dict) else None
            if isinstance(m, str) and m.strip():
                return m.strip()
            return ROLE_FALLBACK_MODEL.get(role, "qwen2.5-coder:14b")

        a_model = _effective_model("architect_model", "architect")
        c_model = _effective_model("coder_model", "coder")
        i_model = _effective_model("inspector_model", "inspector")

        try:
            score = 0
            while iteration <= max_iter:
                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "planning",
                        "iteration": iteration,
                        "agent": "architect",
                        "status": "Analyzing System",
                        "content": f"İterasyon {iteration}: planlama…",
                    }
                ) + "\n"
                save_run(
                    project_path,
                    run_id,
                    {
                        "goal": goal,
                        "test_command": test_cmd,
                        "iteration": iteration,
                        "phase": "planning",
                        "current_context": current_context,
                    },
                )

                obs_for_arch = truncate_observation(current_context, max_obs)
                fail_hint = ""
                if observation_has_failures(obs_for_arch):
                    fail_hint = (
                        "Tool run reported failures, POLICY blocks, or missing resources. "
                        "Recover using LIST/READ, smaller steps, or corrected paths."
                    )
                
                if consecutive_failures >= 2:
                    fail_hint += "\n\n[META-REFLECTION WARNING]: Sistemin uyarısı: Üst üste 2+ kez araçların hata veriyor. Algoritma tıkanıklığı! Derin bir nefes al, inat etmeyi bırak ve farklı bir yöntem («[WEB: search]» veya sıfırdan düşünme) dene."

                aut_cfg = CFG.get("autonomy", {})
                arch_state_tail = None
                if aut_cfg.get("inject_agent_state_tail", True):
                    arch_state_tail = read_agent_state_tail(
                        project_path, int(aut_cfg.get("agent_state_max_bytes", 4000))
                    )
                
                repo_skeleton = generate_repo_map(project_path, goal=goal)
                
                arch_prompt = architect_user_prompt(
                    goal,
                    obs_for_arch,
                    iteration,
                    last_feedback,
                    last_score,
                    fail_hint,
                    arch_state_tail,
                    repo_skeleton,
                )
                
                # ~~~~~ ARCHITECT PHASE ~~~~~
                yield json.dumps({
                    "type": "agent_switch",
                    "agent": "architect",
                    "status": "Mimar düşünüyor..."
                }) + "\n"

                arch_msgs = [
                    {"role": "system", "content": ARCHITECT_SYSTEM + "\n\n" + agent_guide_full},
                    {"role": "user", "content": arch_prompt}
                ]
                
                plan_raw = chat_completion(
                    messages=arch_msgs,
                    model=a_model,
                    temperature=0.2,
                    max_tokens=4000,
                    ollama_role="architect",
                )
                plan = _strip_cfg(plan_raw)
                
                # V15.4: Architect Zero-Question Kalkanı
                m_ask = re.search(r"\[\s*ASK_USER\s*:\s*(.*?)\s*\]", plan, re.IGNORECASE | re.DOTALL)
                if m_ask:
                    ask_q = m_ask.group(1).strip()
                    is_legit_secret_request = bool(re.search(r'(api|key|password|credential|token|secret)', ask_q, re.IGNORECASE))
                    if not is_legit_secret_request:
                        plan += f"\n\n[SYSTEM FATAL ERROR]: As the Architect, you illegally tried to ask the user: '{ask_q}'. You are strictly forbidden from asking the user! The Coder MUST ignore your question, make an educated guess, and write the code immediately!"
                        plan_raw = plan
                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "planning",
                        "iteration": iteration,
                        "agent": "architect",
                        "status": "Strategic Plan",
                        "content": plan_raw,
                    }
                ) + "\n"

                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "executing",
                        "iteration": iteration,
                        "agent": "coder",
                        "status": "Executing Tools",
                        "content": "Araçlar çalıştırılıyor…",
                    }
                ) + "\n"
                coder_prompt = coder_user_prompt(plan, goal, repo_skeleton, workspace_root=project_path) + "\n\n" + agent_guide_full
                
                # V14: Auto-Versioning (Git Time Travel) snapshot before coder executes
                try:
                    from hivecenter.vc import auto_commit
                    auto_commit(project_path, run_id, iteration)
                except Exception:
                    pass
                
                coder_msgs = [
                    {"role": "system", "content": CODER_SYSTEM + "\n\n" + agent_guide_full},
                    {"role": "user", "content": coder_prompt}
                ]

                coding_raw = chat_completion(
                    messages=coder_msgs,
                    model=c_model,
                    temperature=0.1,
                    max_tokens=4000,
                    ollama_role="coder",
                )
                coding_res = _strip_cfg(coding_raw)
                
                # V15: Parse test command dynamically
                test_cmd_match = re.search(r"\[\s*SET_TEST_CMD\s*:\s*(.*?)\s*\]", coding_res, re.IGNORECASE)
                if test_cmd_match:
                    test_cmd = test_cmd_match.group(1).strip()
                    yield json.dumps({"run_id": run_id, "phase": "executing", "iteration": iteration, "agent": "system", "status": "Test Gate Set", "content": f"E2E Test command set: {test_cmd}"}) + "\n"

                observation = execute_agent_tools(coding_res, tool_ctx)
                
                if "[LLM_ROUTER_ERROR]" in (coding_res or ""):
                    observation = (
                        (observation + "\n\n") if observation.strip()
                        else ""
                    ) + (
                        "[SYSTEM] LLM hatası (Ollama/API). Zaman aşımıysa: config.json → ollama.request_timeout_sec "
                        "veya ortam OLLAMA_REQUEST_TIMEOUT=1200; yavaş model için ollama.coder.num_ctx / num_predict düşürün. "
                        "Ollama çalışıyor mu: curl $OLLAMA_HOST/api/tags"
                    )
                
                if re.search(r"\[\s*TEMPLATE\s*:", coding_res, re.IGNORECASE) and not re.search(
                    r"\[\s*CREATE\s*:", coding_res, re.IGNORECASE
                ):
                    observation += (
                        "\n\n[SYSTEM — POST-TEMPLATE] TEMPLATE çalıştı; bu turda henüz `[CREATE: ...]` yok. "
                        "Bir sonraki yanıtta mutlaka proje altında tam kaynak dosyası oluştur (örn. `src/App.jsx`). "
                        "Sadece `npm install` tekrarlamak yasak — motor zaten kurulumu dener."
                    )
                
                # V14.0 Zero-Tool Fallback (Self-Healing System Hardening)
                if not observation.strip() and "[DONE" not in coding_res.upper() and "[" not in coding_res and "]" not in coding_res:
                    observation += "\n\n[SYSTEM ERROR - ZERO TOOL DETECTED] You did not use any tools! You MUST format your actions accurately like [SHELL: pwd]. Do not output plain text filler words. Fix your format immediately!"
                elif not observation.strip() and "[DONE" not in coding_res.upper():
                    observation += "\n\n[SYSTEM ERROR - NO VALID TOOL] No valid tool blocks were detected in your response. Ensure you use exact syntax (e.g. [CREATE: path] or [SHELL: cmd])."
                
                if re.search(r"\[\s*SET_TEST_CMD\s*:", coding_res, re.IGNORECASE) and not _coder_did_real_work(
                    coding_res
                ):
                    observation += (
                        "\n\n[SYSTEM — ACTION REQUIRED] Bu turda yalnızca test komutu kaydı var; henüz [SHELL]/[CREATE]/[REPLACE] yok. "
                        "Aynı veya sonraki turda mutlaka dosya yaz veya npm install / build gibi komut çalıştır."
                    )
                
                # V15.7: Lazy-Done Fallback (Kullanıcının "İşi Takip Et" Emri Üzerine Eklendi)
                if _coder_claimed_done(coding_res):
                    if not _coder_did_real_work(coding_res):
                        fail_str = "\n\n[SYSTEM OVERMIND FATAL ERROR] You claimed [DONE] but you did NOT use ANY mutative tools ([CREATE: path], [REPLACE], [SHELL], [PATCH], [MKDIR])! You lied about finishing the task because NO REAL WORK was done! You MUST write code before calling [DONE]!"
                        observation += fail_str
                        # Laziness detected: Remove [DONE] so it doesn't pass the check below and end the iteration
                        coding_res = re.sub(r'\[\s*DONE\b.*?\]', '[LAZY_DONE_REJECTED]', coding_res, flags=re.IGNORECASE)
                        coding_raw = re.sub(r'\[\s*DONE\b.*?\]', '[LAZY_DONE_REJECTED]', coding_raw, flags=re.IGNORECASE)

                # V15: E2E Gate before DONE
                done_match = re.search(r"\[DONE(?:\:\s*(.*?))?\]", coding_res, re.IGNORECASE)
                if bool(done_match) and test_cmd and str(test_cmd).strip() and not observation.startswith("USER_INPUT_REQUIRED|||"):
                    yield json.dumps({"run_id": run_id, "phase": "executing", "agent": "system", "status": "E2E Gate Testing", "content": f"Running E2E tests: {test_cmd}"}) + "\n"
                    try:
                        import subprocess
                        t_res = subprocess.run(test_cmd, shell=True, capture_output=True, text=True, cwd=project_path, timeout=60)
                        if t_res.returncode != 0:
                            fail_str = f"\n\n[SYSTEM E2E GATE REJECTION] You attempted to finish, but the required test suite ({test_cmd}) FAILED (Code {t_res.returncode})!\nError Output:\n{t_res.stderr}\n{t_res.stdout}\nYOU MUST FIX THE ERRORS BEFORE CALLING [DONE]."
                            observation += fail_str
                            coding_res = coding_res.replace("[DONE]", "[ATTEMPTED_DONE_BUT_FAILED]")
                            coding_raw = coding_raw.replace("[DONE]", "[ATTEMPTED_DONE_BUT_FAILED]")
                        else:
                            observation += f"\n\n[SYSTEM E2E GATE SUCCESS] The required test suite passed flawlessly. You are cleared for [DONE]."
                    except Exception as e:
                        observation += f"\n\n[SYSTEM E2E GATE REJECTION] Test command crashed or timed out: {e}"
                
                
                if observation.startswith("USER_INPUT_REQUIRED|||"):
                    rest = observation[len("USER_INPUT_REQUIRED|||") :]
                    if HIVE_ASK_USER_OBS_SEPARATOR in rest:
                        question, tool_before = rest.split(HIVE_ASK_USER_OBS_SEPARATOR, 1)
                        question = question.strip()
                        ans = (
                            f"\n\n--- Step {iteration} Coder Action (PAUSED) ---\n{coding_res}\n\n"
                            f"--- Tool output before pause ---\n{tool_before}\n\n"
                            f"Agent asked: {question}\n\n"
                            f"(Waiting for user response. When resumed, User Goal/Reply will be appended.)"
                        )
                    else:
                        question = rest
                        ans = f"\n\n--- Step {iteration} Coder Action (PAUSED) ---\n{coding_res}\nAgent asked: {question}\n\n(Waiting for user response. When resumed, User Goal/Reply will be appended.)"
                    save_run(
                        project_path,
                        run_id,
                        {
                            "goal": goal,
                            "test_command": test_cmd,
                            "iteration": iteration,
                            "phase": "blocked",
                            "current_context": current_context + ans,
                            "last_perfection": last_score,
                            "consecutive_failures": consecutive_failures,
                        }
                    )
                    yield json.dumps({
                        "run_id": run_id,
                        "phase": "blocked",
                        "agent": "system",
                        "status": "User Input Required",
                        "content": question
                    }) + "\n"
                    return
                
                # V12: Format Enforcer Micro-Loop (Catches missing brackets/hallucinations)
                format_retries = 0
                while format_retries < 2 and observation.startswith("(no tool invocations"):
                    yield json.dumps({
                        "run_id": run_id,
                        "phase": "executing",
                        "iteration": iteration,
                        "agent": "coder",
                        "status": f"Syntax Correction ({format_retries+1}/2)",
                        "content": "Ajan format hatası yaptı (hiçbir araç kodu kullanmadı). Yeniden yazmaya zorlanıyor...",
                    }) + "\n"
                    
                    coder_prompt_format = (
                        f"SYSTEM/PARSER ERROR: You did not output ANY valid tool tags (like [LIST: path] or [CREATE: path]). "
                        f"Your entire response was ignored because you used plain conversational text without brackets.\n\n"
                        f"REWRITE your last response using ONLY the exact required tool syntax! If you don't know what to do, use [LIST] or [READ]!\n\n"
                        f"AVAILABLE TOOLS:\n{tools_block}"
                    )
                    
                    coder_msgs_retry = [
                        {"role": "system", "content": CODER_SYSTEM + "\n\n" + agent_guide_full},
                        {"role": "user", "content": coder_prompt_format}
                    ]
                    coding_raw_retry = chat_completion(
                        messages=coder_msgs_retry,
                        model=c_model,
                        temperature=0.1,
                        max_tokens=4000,
                        ollama_role="coder",
                    )
                    coding_res_retry = _strip_cfg(coding_raw_retry)
                    new_observation = execute_agent_tools(coding_res_retry, tool_ctx)
                    
                    coding_raw += f"\n\n-- SYNTAX FIX {format_retries+1} --\n{coding_raw_retry}"
                    coding_res += f"\n\n-- SYNTAX FIX {format_retries+1} --\n{coding_res_retry}"
                    observation = new_observation
                    
                    format_retries += 1
                
                canvas_syncs = re.findall(r"\[\[CANVAS_SYNC:\s*(.+?)\]\]", observation)
                canvas_paths = [p.strip() for p in canvas_syncs] if canvas_syncs else []
                
                
                # Fast-Fail Micro-Loop (0-to-1 app building helper)
                # If command fails, give the coder up to 2 fast retries without bothering the architect.
                retries = 0
                while retries < 2 and observation_has_failures(observation):
                    yield json.dumps({
                        "run_id": run_id,
                        "phase": "executing",
                        "iteration": iteration,
                        "agent": "coder",
                        "status": f"Auto-Fixing Error ({retries+1}/2)",
                        "content": f"Ajan hatayı fark etti, kendi kendine düzeltiyor...\n{observation[:200]}",
                    }) + "\n"
                    
                    coder_prompt_retry = (
                        f"Your last tools resulted in FAILURES:\n{observation}\n\n"
                        f"DO NOT wait for the architect. Fix the code or command IMMEDIATELY using your tools."
                        f"\n\nAVAILABLE TOOLS:\n{tools_block}"
                    )
                    coder_msgs_retry = [
                        {"role": "system", "content": CODER_SYSTEM + "\n\n" + agent_guide_full},
                        {"role": "user", "content": coder_prompt_retry}
                    ]
                    coding_raw_retry = chat_completion(
                        messages=coder_msgs_retry,
                        model=c_model,
                        temperature=0.1,
                        max_tokens=4000,
                        ollama_role="coder",
                    )
                    coding_res_retry = _strip_cfg(coding_raw_retry)
                    new_observation = execute_agent_tools(coding_res_retry, tool_ctx)
                    
                    coding_res += f"\n\n-- FAST-FAIL RETRY {retries+1} ACTION --\n{coding_res_retry}"
                    observation += f"\n\n-- FAST-FAIL RETRY {retries+1} RESULT --\n{new_observation}"
                    
                    if not observation_has_failures(new_observation):
                        break
                    retries += 1
                
                # Meta-reflection tracking
                if observation_has_failures(observation):
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                current_context = current_context + f"\n\n--- Step {iteration} Coder Action ---\n{coding_res}\n--- Step {iteration} Tool Results ---\n{observation}"

                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "executing",
                        "iteration": iteration,
                        "agent": "coder",
                        "status": "Action Completed",
                        "canvas_sync": canvas_paths,
                        "content": f"{coding_raw}\n\nRESULT:\n{observation}",
                    }
                ) + "\n"

                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "verifying",
                        "iteration": iteration,
                        "agent": "inspector",
                        "status": "QA Review",
                        "content": "Müfettiş değerlendirmesi…",
                    }
                ) + "\n"
                eval_obs = truncate_observation(observation, int(max_obs * 0.85))
                eval_prompt = inspector_user_prompt(goal, eval_obs)
                
                inspector_msgs = [
                    {"role": "system", "content": INSPECTOR_SYSTEM + "\n\n" + agent_guide_full},
                    {"role": "user", "content": eval_prompt}
                ]
                eval_raw = chat_completion(
                    messages=inspector_msgs,
                    model=i_model,
                    temperature=0.1,
                    max_tokens=4000,
                    ollama_role="inspector",
                )
                eval_for_score = _strip_cfg(eval_raw)
                score = extract_perfection_score(eval_for_score)
                if score == 0 and eval_for_score and not re.search(r"PERFECTION\s*:", eval_for_score, re.I):
                    score = 50
                eval_res = eval_raw

                yield json.dumps(
                    {
                        "run_id": run_id,
                        "phase": "verifying",
                        "iteration": iteration,
                        "agent": "inspector",
                        "status": "Report",
                        "score": score,
                        "content": eval_res,
                    }
                ) + "\n"

                if CFG.get("autonomy", {}).get("append_agent_state_md", True):
                    try:
                        append_agent_state_log(
                            project_path,
                            run_id,
                            iteration,
                            score,
                            (eval_for_score or "")[:240].replace("\n", " "),
                        )
                    except Exception:
                        pass

                last_feedback = (eval_res or "")[:12000]
                last_score = score

                verify_passed = True
                verify_out = ""
                if test_cmd and str(test_cmd).strip():
                    sh = CFG.get("shell", {})
                    verify_passed, verify_out, _ = run_verify_command(
                        str(test_cmd).strip(),
                        project_path,
                        int(sh.get("timeout_sec", 120)) + 60,
                        int(sh.get("max_output_bytes", 262144)),
                    )
                    yield json.dumps(
                        {
                            "run_id": run_id,
                            "phase": "verifying",
                            "iteration": iteration,
                            "agent": "gate",
                            "status": "Verify",
                            "verify_passed": verify_passed,
                            "content": verify_out[:8000],
                        }
                    ) + "\n"

                next_it = iteration + 1
                
                # V19/V20 Event-Driven PTY & GHOST Alarms
                from hivecenter.pty_manager import GLOBAL_PTY
                from hivecenter.ghost_observer import GLOBAL_GHOST
                
                alarms = GLOBAL_PTY.pull_alarms()
                alarms.extend(GLOBAL_GHOST.pull_alarms())
                if alarms:
                    current_context += "\n\n" + "\n".join(alarms) + "\n"
                
                # V14: Auto-Memory Compaction (Infinite Context)
                if next_it % 7 == 0 and len(current_context) > 12000:
                    yield json.dumps({
                        "run_id": run_id,
                        "phase": "executing",
                        "iteration": iteration,
                        "agent": "system",
                        "status": "Memory Compaction",
                        "content": "Bağlam çok şiştiği için eski anılar sıkıştırılıyor (Infinite Context)..."
                    }) + "\n"
                    summarizer_prompt = f"Please summarize the following project history into a dense, highly technical context block. Retain all technical facts, file paths, and current goals, but strip out verbose tool output and narration.\n\n{current_context}"
                    summarizer_msgs = [
                        {"role": "system", "content": "You are a memory compaction core."},
                        {"role": "user", "content": summarizer_prompt}
                    ]
                    compacted = chat_completion(
                        messages=summarizer_msgs,
                        model=a_model, # Using architect model for summarization
                        temperature=0.2,
                        max_tokens=4000,
                        ollama_role="architect",
                    )
                    current_context = f"--- [COMPACTED HISTORY SUMMARY (Up to Iteration {iteration})] ---\n{compacted}\n--- [RECENT STEPS START HERE] ---\n"

                # Yalnızca kodcu çıktısındaki [DONE] run'ı bitirir (müfettiş yanıtındaki [DONE] kelimesi değil).
                done_flag = _coder_claimed_done(coding_res)
                if done_flag and score < 40:
                    done_flag = False
                    current_context += (
                        "\n\n[SYSTEM OVERRIDE] [DONE] yok sayıldı: PERFECTION < 40. "
                        "Çalışan kod / geçerli doğrulama olmadan görev tamamlanamaz; sonraki iterasyonda devam et.\n"
                    )

                save_run(
                    project_path,
                    run_id,
                    {
                        "goal": goal,
                        "test_command": test_cmd,
                        "iteration": next_it,
                        "phase": "between_iterations",
                        "current_context": current_context,
                        "last_perfection": score,
                        "last_inspector_feedback": last_feedback,
                        "consecutive_failures": consecutive_failures,
                    },
                )

                # V9.1: Ajanın kapanış metnini (Rapor) UI'da göstermek için tam logu al.
                done_msg = coding_res.strip()
                threshold_met = score >= threshold
                verify_blocks = require_test and test_cmd and not verify_passed

                iteration = next_it

                if done_flag:
                    if verify_blocks:
                        yield json.dumps(
                            {
                                "run_id": run_id,
                                "phase": "blocked",
                                "agent": "gate",
                                "status": "Verify failed",
                                "content": "require_pass_for_done: test failed; not completing.",
                            }
                        ) + "\n"
                        save_run(
                            project_path,
                            run_id,
                            {"goal": goal, "phase": "failed", "iteration": iteration - 1, "current_context": current_context}
                        )
                        return
                    save_run(
                        project_path,
                        run_id,
                        {"goal": goal, "phase": "completed", "iteration": iteration - 1, "current_context": current_context, "last_perfection": score},
                    )
                    append_entry(
                        project_path,
                        {"goal": goal, "perfection": score, "note": "run completed [DONE]", "run_id": run_id},
                    )
                    yield json.dumps(
                        {"run_id": run_id, "phase": "completed", "agent": "system", "status": "Done", "content": done_msg}
                    ) + "\n"
                    return

                if threshold_met:
                    if verify_blocks:
                        yield json.dumps(
                            {
                                "run_id": run_id,
                                "phase": "blocked",
                                "agent": "gate",
                                "status": "Verify failed",
                                "content": "Perfection threshold met but verify failed.",
                            }
                        ) + "\n"
                        save_run(
                            project_path,
                            run_id,
                            {
                                "goal": goal,
                                "phase": "blocked",
                                "iteration": iteration - 1,
                                "current_context": current_context,
                                "last_perfection": score,
                            },
                        )
                        return
                    save_run(
                        project_path,
                        run_id,
                        {"goal": goal, "phase": "completed", "iteration": iteration - 1, "current_context": current_context, "last_perfection": score},
                    )
                    append_entry(
                        project_path,
                        {"goal": goal, "perfection": score, "note": "threshold complete", "run_id": run_id},
                    )
                    yield json.dumps(
                        {
                            "run_id": run_id,
                            "phase": "completed",
                            "agent": "inspector",
                            "status": "Threshold met",
                            "content": f"Perfection ≥{threshold}; döngü sonlandı.",
                        }
                    ) + "\n"
                    return

            save_run(
                project_path,
                run_id,
                {"goal": goal, "phase": "completed", "iteration": max_iter, "current_context": current_context, "last_perfection": score},
            )
            append_entry(
                project_path,
                {
                    "goal": goal,
                    "perfection": score,
                    "note": f"max iterations ({max_iter}) — son müfettiş skoru",
                    "run_id": run_id,
                },
            )
            yield json.dumps(
                {"run_id": run_id, "phase": "completed", "agent": "system", "status": "Max iterations", "content": str(max_iter)}
            ) + "\n"
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:1800]}"
            yield json.dumps(
                {
                    "run_id": run_id,
                    "phase": "failed",
                    "agent": "system",
                    "status": "Error",
                    "content": msg,
                }
            ) + "\n"
            try:
                save_run(
                    project_path,
                    run_id,
                    {
                        "goal": goal,
                        "phase": "failed",
                        "iteration": iteration,
                        "current_context": current_context,
                    },
                )
            except Exception:
                pass
            try:
                append_entry(
                    project_path,
                    {
                        "goal": goal,
                        "note": "run failed: " + msg[:400],
                        "run_id": run_id,
                    },
                )
            except Exception:
                pass

    return Response(generate(), mimetype="application/x-ndjson")


@app.route("/api/system", methods=["GET"])
def api_system():
    reload_config()
    return jsonify(get_system_metrics())


@app.route("/api/health", methods=["GET"])
def api_health():
    reload_config()
    m = get_system_metrics()
    ok, lat_ms, n_ollama = ollama_health_metrics()
    return jsonify(
        {
            "hivecenter_version": HIVECENTER_VERSION,
            "cpu_percent": m.get("cpu_percent"),
            "memory_percent": m.get("memory_percent"),
            "gpu": m.get("gpu"),
            "ollama_ok": ok,
            "ollama_latency_ms": lat_ms,
            "ollama_model_count": n_ollama,
            "workspace": BASE_WORKSPACE,
        }
    )

@app.route("/api/models", methods=["GET"])
def api_models():
    models = [
        "gpt-4o", "gpt-4o-mini", 
        "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307",
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"
    ]
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as res:
            if res.status == 200:
                data = json.loads(res.read().decode())
                for m in data.get("models", []):
                    name = m.get("name")
                    if name:
                        models.append(name)
    except Exception:
        models.append("Yüklenemedi (Ollama Kapalı)")
    
    return jsonify({"models": models})

_UI_CONFIG_KEYS = frozenset(
    {
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "architect_model",
        "coder_model",
        "inspector_model",
        "pull_model_name",
    }
)


def _default_role_model(role: str) -> str:
    if isinstance(MODELS, dict):
        m = MODELS.get(role)
        if isinstance(m, str) and m.strip():
            return m.strip()
    return ROLE_FALLBACK_MODEL.get(role, "qwen2.5-coder:14b")


def _ui_settings_payload() -> dict:
    """Dashboard'un beklediği düz alanlar + repo config.json'dan varsayılan model adları."""
    reload_config()
    llm = load_llm_config()
    nested = llm.get("models") if isinstance(llm.get("models"), dict) else {}

    def pick(flat_key: str, role: str) -> str:
        v = llm.get(flat_key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        r = nested.get(role)
        if isinstance(r, str) and r.strip():
            return r.strip()
        d = _default_role_model(role)
        return d if isinstance(d, str) else ROLE_FALLBACK_MODEL.get(role, "qwen2.5-coder:14b")

    meta = api_key_sources_meta()
    return {
        "architect_model": pick("architect_model", "architect"),
        "coder_model": pick("coder_model", "coder"),
        "inspector_model": pick("inspector_model", "inspector"),
        "openai_api_key": (llm.get("openai_api_key") or "") if isinstance(llm.get("openai_api_key"), str) else "",
        "anthropic_api_key": (llm.get("anthropic_api_key") or "") if isinstance(llm.get("anthropic_api_key"), str) else "",
        "gemini_api_key": (llm.get("gemini_api_key") or "") if isinstance(llm.get("gemini_api_key"), str) else "",
        "pull_model_name": (llm.get("pull_model_name") or "") if isinstance(llm.get("pull_model_name"), str) else "",
        "openai_key_source": meta.get("openai_key_source", "none"),
        "anthropic_key_source": meta.get("anthropic_key_source", "none"),
        "gemini_key_source": meta.get("gemini_key_source", "none"),
    }


@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    """Tek uç: ayarlar UI ile uyumlu düz JSON; POST sadece bilinen anahtarları yazar."""
    config_file = os.path.expanduser("~/.hivecenter_config.json")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        incoming = {}
        for k in _UI_CONFIG_KEYS:
            if k in data:
                incoming[k] = data[k]
        for k in ("architect_model", "coder_model", "inspector_model"):
            if k in incoming:
                v = incoming[k]
                s = (v if isinstance(v, str) else str(v)).strip()
                if not s:
                    incoming.pop(k, None)
                else:
                    incoming[k] = s
        for k in ("openai_api_key", "anthropic_api_key", "gemini_api_key"):
            if k in incoming and isinstance(incoming[k], str):
                incoming[k] = incoming[k].strip()
        if "pull_model_name" in incoming and isinstance(incoming["pull_model_name"], str):
            incoming["pull_model_name"] = incoming["pull_model_name"].strip()

        existing: dict = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if not isinstance(existing, dict):
                        existing = {}
            except Exception:
                existing = {}
        existing.update(incoming)
        
        out: dict = {}
        for k in _UI_CONFIG_KEYS:
            out[k] = existing.get(k, "")
            if not isinstance(out[k], str):
                out[k] = str(out[k]) if out[k] is not None else ""
        for k, role in (("architect_model", "architect"), ("coder_model", "coder"), ("inspector_model", "inspector")):
            if not str(out.get(k) or "").strip():
                out[k] = _default_role_model(role)
                
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
            
        reload_config()
        return jsonify({"status": "ok"})
    return jsonify(_ui_settings_payload())

@app.route("/api/pull", methods=["POST"])
def pull_model():
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip() if isinstance(body, dict) else ""
    if not model:
        return jsonify({"error": "No model specified"}), 400
    try:
        import subprocess
        # Arka planda başlatalım
        subprocess.Popen(["ollama", "pull", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"status": f"Ollama is pulling '{model}' in the background..."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/runs", methods=["GET"])
def api_runs_list():
    reload_config()
    try:
        lim = min(50, max(1, int(request.args.get("limit", 25))))
    except ValueError:
        lim = 25
        
    p_folder = request.args.get("project_folder", "").strip()
    if p_folder:
        if os.path.isabs(p_folder):
            target_path = p_folder
        else:
            target_path = os.path.join(BASE_WORKSPACE, p_folder)
        return jsonify({"runs": list_recent_runs(target_path, lim)})
        
    return jsonify({"runs": list_recent_runs(BASE_WORKSPACE, lim)})


@app.route("/api/server-config", methods=["GET"])
def api_server_config():
    """Salt okunur: workspace, run eşikleri vb. (debug / ileride UI)."""
    reload_config()
    return jsonify(
        {
            "workspace_root": CFG["workspace_root"],
            "allowed_roots": CFG.get("allowed_roots", []),
            "run": CFG.get("run", {}),
            "verify": {k: v for k, v in CFG.get("verify", {}).items()},
            "models": CFG.get("models", {}),
            "tools": [
                "LIST",
                "STAT",
                "GLOB",
                "READ",
                "CREATE",
                "PATCH",
                "MKDIR",
                "SHELL",
                "SEARCH",
                "SEMANTIC",
                "GIT",
            ],
            "glob": CFG.get("glob", {}),
            "patch": CFG.get("patch", {}),
            "semantic": {k: v for k, v in CFG.get("semantic", {}).items()},
            "shell_approval_triggers": CFG.get("shell", {}).get("approval_triggers", []),
            "ollama": CFG.get("ollama", {}),
            "autonomy": CFG.get("autonomy", {}),
            "goal_templates": CFG.get("ui", {}).get("goal_templates", []),
        }
    )


def _clip_audit_entry(entry: dict) -> dict:
    e = dict(entry)
    d = e.get("detail")
    if isinstance(d, str) and len(d) > 900:
        e["detail"] = d[:900] + "…"
    return e


@app.route("/api/audit", methods=["GET"])
def api_audit_recent():
    reload_config()
    try:
        lim = min(200, max(1, int(request.args.get("limit", 80))))
    except ValueError:
        lim = 80
    path = CFG["_audit_log_abs"]
    entries = read_recent_audit_entries(path, lim)
    return jsonify(
        {
            "entries": [_clip_audit_entry(e) for e in entries],
            "path": CFG.get("audit", {}).get("log_path", "logs/audit.ndjson"),
        }
    )


@app.route("/api/agent-state", methods=["GET"])
def api_agent_state():
    reload_config()
    aut = CFG.get("autonomy", {})
    nbytes = int(aut.get("agent_state_max_bytes", 4000))
    tail = read_agent_state_tail(BASE_WORKSPACE, nbytes) if aut.get("inject_agent_state_tail", True) else None
    return jsonify({"tail": tail, "path": "AGENT_STATE.md"})


@app.route("/api/memory", methods=["GET"])
def api_memory_get():
    reload_config()
    return jsonify(read_memory(BASE_WORKSPACE))


@app.route("/api/memory", methods=["POST"])
def api_memory_post():
    reload_config()
    body = request.json or {}
    append_entry(BASE_WORKSPACE, body)
    return jsonify({"ok": True})


@app.route("/api/approvals", methods=["GET"])
def api_approvals_list():
    reload_config()
    pending = list_pending(BASE_WORKSPACE)
    recent = list_all(BASE_WORKSPACE, 80)
    return jsonify(
        {
            "enabled": True,
            "pending": pending,
            "approved_ready": list_approved_ready(BASE_WORKSPACE),
            "recent": recent,
        }
    )


@app.route("/api/approvals/request", methods=["POST"])
def api_approvals_request():
    reload_config()
    body = request.json or {}
    cmd = (body.get("command") or "").strip()
    if not cmd:
        return jsonify({"error": "command required"}), 400
    rid = (body.get("run_id") or "").strip() or None
    note = (body.get("note") or "").strip()
    aid = add_manual_request(BASE_WORKSPACE, rid, cmd, note)
    return jsonify({"id": aid})


@app.route("/api/approvals/<aid>/resolve", methods=["POST"])
def api_approvals_resolve(aid):
    reload_config()
    body = request.json or {}
    approved = bool(body.get("approved"))
    ok, msg = approval_resolve(BASE_WORKSPACE, aid, approved)
    if not ok:
        return jsonify({"error": msg}), 404
    return jsonify({"ok": True, "id": aid, "approved": approved})


@app.route("/api/approvals/<aid>/execute", methods=["POST"])
def api_approvals_execute(aid):
    reload_config()
    rec = get_record(BASE_WORKSPACE, aid)
    if not rec:
        return jsonify({"error": "not found"}), 404
    if rec.get("status") != "approved":
        return jsonify({"error": "record must be approved first"}), 400
    if rec.get("executed_at"):
        return jsonify({"error": "already executed", "output": rec.get("execution_output")}), 400
    cmd = (rec.get("command") or "").strip()
    if not cmd:
        return jsonify({"error": "empty command"}), 400
    sh = CFG.get("shell", {})
    extra = list(sh.get("hard_deny_substrings", []))
    denied, reason = is_hard_denied(cmd, extra)
    if denied:
        return jsonify({"error": reason}), 403
    timeout = int(sh.get("execute_approved_timeout_sec", 300))
    max_out = int(sh.get("max_output_bytes", 262144))
    audit = AuditLogger(CFG["_audit_log_abs"], CFG.get("audit", {}).get("redact", True))
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=BASE_WORKSPACE,
            timeout=timeout,
        )
        out = (res.stdout or "") + (res.stderr or "")
        if len(out.encode("utf-8", errors="replace")) > max_out:
            out = out[:max_out] + "\n... [truncated]"
        ok_run = res.returncode == 0
        mark_executed(BASE_WORKSPACE, aid, res.returncode, out, ok_run)
        audit.append(
            {
                "correlation_id": rec.get("run_id") or "approval-execute",
                "tool": "APPROVED_SHELL",
                "ok": ok_run,
                "detail": f"id={aid} code={res.returncode}",
            }
        )
        return jsonify(
            {
                "ok": True,
                "returncode": res.returncode,
                "output": out,
                "id": aid,
            }
        )
    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT after {timeout}s"
        mark_executed(BASE_WORKSPACE, aid, -1, msg, False)
        audit.append(
            {
                "correlation_id": rec.get("run_id") or "approval-execute",
                "tool": "APPROVED_SHELL",
                "ok": False,
                "detail": f"id={aid} timeout",
            }
        )
        return jsonify({"ok": False, "error": "timeout", "output": msg}), 500


@app.route("/api/runs/<run_id>", methods=["GET"])
def api_run_get(run_id):
    reload_config()
    st = load_run(BASE_WORKSPACE, run_id)
    if not st:
        return jsonify({"error": "not found"}), 404
    return jsonify(st)


@app.route("/dashboard/<path:filename>")
def serve_dashboard(filename):
    return send_from_directory(os.path.join(ROOT, "dashboard"), filename)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HiveCenter Flask API and dashboard backend")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (use 0.0.0.0 in containers)")
    parser.add_argument("--port", type=int, default=5001, help="HTTP port")
    ns = parser.parse_args()
    app.run(host=ns.host, port=ns.port)
