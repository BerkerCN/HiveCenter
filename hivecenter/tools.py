import datetime
import glob as globmod
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from hivecenter.approvals_store import add_pending
from hivecenter.audit import AuditLogger
from hivecenter.patch_apply import apply_unified_diff
from hivecenter.policy import PolicyContext

# hive_server must parse USER_INPUT_REQUIRED with this separator to recover tool output before pause
HIVE_ASK_USER_OBS_SEPARATOR = "\n<<<HIVE_USER_QUESTION_END>>>\n"

# If [ASK_USER] text matches, do not block the run — coder should act autonomously instead
def _goal_suggests_static_or_single_html(goal: str) -> bool:
    """React/Vite iskeleti bu hedeflerle çakışır; TEMPLATE react-vite atlanır."""
    g = (goal or "").lower()
    needles = (
        "single html",
        "tek html",
        "one file",
        "html file",
        "tek dosya",
        "tek dosyada",
        "bir html",
        "single file",
        "game.html",
        "index.html",
        "plain html",
        "vanilla",
        "no react",
        "without react",
        "sadece html",
        "tek bir html",
        "tek sayfa",
        "single page html",
        "inline css",
        "inline javascript",
    )
    if any(n in g for n in needles):
        return True
    # Basit oyun + HTML/tek dosya imaı (hedef metninde geçer)
    if "snake" in g and any(x in g for x in ("html", "tek", "single", "one file", "bir dosya", "canvas")):
        return True
    return False


_ASK_USER_AUTONOMY_DENY = re.compile(
    r"devam\s+et|devam\s+etmek|continue\??|istiyor\s+musun|ister\s+misin|ne\s+yapalım|"
    r"what\s+should\s+(we|i)|what\s+do\s+you\s+want|shall\s+i\s+continue",
    re.I,
)


@dataclass
class ToolContext:
    workspace_root: str
    policy: PolicyContext
    audit: Optional[AuditLogger]
    correlation_id: str
    shell_timeout: int
    shell_max_out: int
    shell_deny: List[str]
    read_max_bytes: int
    search_cfg: dict
    patch_cfg: dict = field(default_factory=dict)
    semantic_cfg: dict = field(default_factory=dict)
    glob_cfg: dict = field(default_factory=dict)
    embed_model: str = "nomic-embed-text"
    approval_triggers: List[str] = field(default_factory=list)
    cursor_master: dict = field(default_factory=dict)
    user_goal: str = ""


def _parse_read_spec(spec: str) -> Tuple[str, Optional[int], Optional[int]]:
    """[READ: path#L10-L80] → path, start line (1-based), end line inclusive."""
    s = spec.strip()
    m = re.match(r"^(.+?)#L(\d+)-L(\d+)$", s, re.IGNORECASE | re.DOTALL)
    if m:
        p, a, b = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        if a > 0 and b >= a:
            return p, a, b
    return s, None, None


def _shell_allowed(cmd: str, deny: List[str]) -> Tuple[bool, str]:
    c = cmd.strip()
    low = c.lower()
    for d in deny:
        if d.strip() and d.strip().lower() in low:
            return False, f"shell denied: matched blocked pattern {d!r}"
    return True, ""


def _needs_approval(cmd: str, triggers: List[str]) -> bool:
    if not triggers:
        return False
    low = cmd.lower()
    for t in triggers:
        if t and str(t).lower() in low:
            return True
    return False


def _truncate(s: str, max_bytes: int) -> Tuple[str, bool]:
    b = s.encode("utf-8", errors="replace")
    if len(b) <= max_bytes:
        return s, False
    cut = max_bytes
    return b[:cut].decode("utf-8", errors="replace") + "\n... [output truncated]", True


def execute_agent_tools(text: str, ctx: ToolContext) -> str:
    """LIST STAT GLOB READ CREATE PATCH MKDIR SHELL SEARCH SEMANTIC GIT."""
    observations: List[str] = []
    ws = ctx.workspace_root

    def log(tool: str, ok: bool, detail: str, extra: Optional[dict] = None):
        if ctx.audit:
            e = {
                "correlation_id": ctx.correlation_id,
                "tool": tool,
                "ok": ok,
                "detail": detail[:8000],
            }
            if extra:
                e.update(extra)
            ctx.audit.append(e)

    # 1. LIST
    for m in re.finditer(r"\[\s*LIST\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        rel = m.group(1).strip()
        path, err = ctx.policy.resolve_safe(ws, rel)
        if err:
            observations.append(f"POLICY: LIST {rel}: {err}")
            log("LIST", False, err, {"path": rel})
            continue
        try:
            files = os.listdir(path)
            observations.append(f"FILES IN {rel}: {', '.join(files)}")
            log("LIST", True, f"ok {rel}", {"path": path})
        except OSError as e:
            observations.append(f"FAILED to list {rel}: {e}")
            log("LIST", False, str(e), {"path": rel})

    # 2. STAT
    for m in re.finditer(r"\[\s*STAT\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        rel = m.group(1).strip()
        path, err = ctx.policy.resolve_safe(ws, rel)
        if err:
            observations.append(f"POLICY: STAT {rel}: {err}")
            log("STAT", False, err)
            continue
        try:
            st = os.stat(path)
            isdir = os.path.isdir(path)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            observations.append(
                f"STAT {rel}: size={st.st_size} bytes; mtime_utc={mtime}; is_dir={isdir}"
            )
            log("STAT", True, f"ok {rel}")
        except OSError as e:
            observations.append(f"FAILED STAT {rel}: {e}")
            log("STAT", False, str(e))

    # 3. GLOB
    max_glob = int(ctx.glob_cfg.get("max_matches", 200))
    for m in re.finditer(r"\[\s*GLOB\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        raw_pat = m.group(1).strip()
        if not raw_pat or ".." in raw_pat.replace("\\", "/"):
            observations.append("GLOB: invalid or unsafe pattern (no ..)")
            log("GLOB", False, "bad pattern")
            continue
        _, err = ctx.policy.path_allowed(ws)
        if err:
            observations.append(f"POLICY: GLOB {err}")
            log("GLOB", False, err)
            continue
        pat = raw_pat if os.path.isabs(raw_pat) and ctx.policy.cfg.get("god_mode") else raw_pat.lstrip("/\\")
        pat_dir = pat if os.path.isabs(pat) else os.path.join(ws, pat)
        god_mode = ctx.policy.cfg.get("god_mode", False)
        
        try:
            matches = globmod.glob(pat_dir, recursive=True)
            ws_real = os.path.realpath(ws)
            safe: List[str] = []
            for p in matches:
                if len(safe) >= max_glob:
                    break
                rp = os.path.realpath(p)
                if not god_mode and rp != ws_real and not rp.startswith(ws_real + os.sep):
                    continue
                
                rel = rp if god_mode else os.path.relpath(p, ws)
                if not god_mode and rel.startswith(".."):
                    continue
                safe.append(rel)
            safe.sort()
            extra = ""
            if len(matches) > len(safe):
                extra = f" (raw {len(matches)} hits; workspace-safe {len(safe)} shown)"
            elif len(matches) > max_glob:
                extra = f" (truncated to {max_glob})"
            observations.append(
                f"GLOB `{raw_pat}`:{extra}\n" + ("\n".join(safe) if safe else "(no matches)")
            )
            log("GLOB", True, f"{len(safe)} matches")
        except Exception as e:
            observations.append(f"GLOB FAILED: {e}")
            log("GLOB", False, str(e))

    # 4. READ
    for m in re.finditer(r"\[\s*READ\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        spec = m.group(1).strip()
        rel, line_start, line_end = _parse_read_spec(spec)
        path, err = ctx.policy.resolve_safe(ws, rel)
        if err:
            observations.append(f"POLICY: READ {spec}: {err}")
            log("READ", False, err)
            continue
        try:
            if line_start is not None and line_end is not None:
                lines_out: List[str] = []
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        if i > line_end:
                            break
                        if i >= line_start:
                            lines_out.append(line.rstrip("\n\r"))
                if not lines_out:
                    observations.append(f"READ {spec}: no lines in range (empty file or past EOF)")
                    log("READ", False, "range empty")
                    continue
                body = "\n".join(lines_out)
                observations.append(f"CONTENT OF {rel} lines {line_start}-{line_end}:\n{body}")
                log("READ", True, f"ok lines {line_start}-{line_end} len={len(body)}")
                continue
            st = os.path.getsize(path)
            if st > ctx.read_max_bytes + 1:
                observations.append(
                    f"READ {rel}: file too large ({st} bytes), max {ctx.read_max_bytes}; use [READ: path#Lstart-Lend]"
                )
                log("READ", False, "too large")
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                body = f.read(ctx.read_max_bytes + 1)
            if len(body) > ctx.read_max_bytes:
                body = body[: ctx.read_max_bytes] + "\n... [truncated]"
            observations.append(f"CONTENT OF {rel}:\n{body}")
            log("READ", True, f"ok bytes={len(body)}")
        except OSError as e:
            observations.append(f"FAILED to read {spec}: {e}")
            log("READ", False, str(e))

    # 5. CREATE
    for m in re.finditer(
        r"\[\s*CREATE\s*:\s*([^\]]+?)\s*\].*?```[a-zA-Z0-9_-]*\s*\r?\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        rel = m.group(1).strip()
        content = m.group(2)
        path, err = ctx.policy.resolve_safe(ws, rel)
        if err:
            observations.append(f"POLICY: CREATE {rel}: {err}")
            log("CREATE", False, err)
            continue
        try:
            if path.endswith(".py"):
                import ast
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    observations.append(f"AST LINTER BLOCKED CREATE {rel}: SyntaxError on line {e.lineno}: {e.msg}\\nFix your code before writing!")
                    log("CREATE", False, f"AST Blocked: {e}")
                    continue
                    
            try:
                from hivecenter.chronos import take_snapshot
                take_snapshot(ws, path)
            except Exception:
                pass
                
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp = path + ".hive.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
            observations.append(f"SUCCESS: {rel} created/updated. [[CANVAS_SYNC: {path}]]")
            log("CREATE", True, f"wrote {len(content)} chars", {"path": rel})
        except OSError as e:
            observations.append(f"FAILED CREATE {rel}: {e}")
            log("CREATE", False, str(e))

    # 6. PATCH (unified diff)
    if ctx.patch_cfg.get("enabled", True):
        for m in re.finditer(
            r"\[\s*REPLACE\s*:\s*([^\]]+?)\s*\]\s*<<<<\s*SEARCH\s*\r?\n(.*?)====(?:\r?\n)?(.*?)>>>>\s*REPLACE",
            text,
            re.DOTALL | re.IGNORECASE,
        ):
            rel_hint = m.group(1).strip()
            search_body = m.group(2)
            replace_body = m.group(3)

            _, err = ctx.policy.path_allowed(ws)
            if err:
                observations.append(f"POLICY: REPLACE {err}")
                log("REPLACE", False, err)
                continue
            
            from hivecenter.patch_apply import apply_search_replace
            ok, msg = apply_search_replace(ws, rel_hint, search_body, replace_body)
            sync_tag = f" [[CANVAS_SYNC: {os.path.join(ws, rel_hint)}]]" if ok else ""
            observations.append(f"REPLACE ({rel_hint}): {'OK' if ok else 'FAIL'} — {msg}{sync_tag}")
            log("REPLACE", ok, msg[:500], {"hint": rel_hint[:200]})
        
        # Legacy PATCH support for backward compatibility if the model forgets
        for m in re.finditer(
            r"\[\s*PATCH\s*:\s*([^\]]*)\s*\]\s*```(?:diff)?\s*\r?\n(.*?)```",
            text,
            re.DOTALL | re.IGNORECASE,
        ):
            rel_hint = m.group(1).strip()
            diff_body = m.group(2).strip()
            if not diff_body:
                continue
            _, err = ctx.policy.path_allowed(ws)
            if err:
                continue
            ok, msg = apply_unified_diff(ws, diff_body)
            observations.append(f"PATCH ({rel_hint or 'diff'}): {'OK' if ok else 'FAIL'} — {msg}")
            log("PATCH", ok, msg[:500], {"hint": rel_hint[:200]})

    # 7. MKDIR
    for m in re.finditer(r"\[\s*MKDIR\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        rel = m.group(1).strip()
        path, err = ctx.policy.resolve_safe(ws, rel)
        if err:
            observations.append(f"POLICY: MKDIR {rel}: {err}")
            log("MKDIR", False, err)
            continue
        try:
            os.makedirs(path, exist_ok=True)
            observations.append(f"MKDIR OK: {rel}")
            log("MKDIR", True, rel)
        except OSError as e:
            observations.append(f"MKDIR FAIL {rel}: {e}")
            log("MKDIR", False, str(e))

    # 8. SHELL
    for m in re.finditer(r"\[\s*SHELL\s*:\s*([^\]]+)\s*\]", text, re.IGNORECASE):
        cmd = m.group(1).strip()
        if _needs_approval(cmd, ctx.approval_triggers):
            aid = add_pending(ws, ctx.correlation_id, cmd, "shell")
            observations.append(
                f"SHELL NOT RUN (approval required): id={aid}\n"
                f"Command was: {cmd[:500]}\n"
                "Resolve via POST /api/approvals/<id>/resolve or dashboard."
            )
            log("SHELL", False, f"approval pending {aid}", {"cmd": cmd[:300]})
            continue
        okp, reason = _shell_allowed(cmd, ctx.shell_deny)
        if not okp:
            observations.append(f"POLICY: SHELL blocked: {reason}")
            log("SHELL", False, reason, {"cmd": cmd[:500]})
            continue
        try:
            # V8.0.1 Fix: NPM ve apt-get gibi araçların progress_bar üretip 
            # subprocess.communicate() kısmını kilitlememesi için CI ortam değişkenleri eklendi.
            env = os.environ.copy()
            env["CI"] = "true"
            env["NO_COLOR"] = "1"
            env["NPM_CONFIG_PROGRESS"] = "false"
            env["NPM_CONFIG_FUND"] = "false"
            env["NPM_CONFIG_AUDIT"] = "false"
            
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=ws,
                timeout=ctx.shell_timeout,
                env=env,
            )
            out = (res.stdout or "") + (res.stderr or "")
            out, trunc = _truncate(out, ctx.shell_max_out)
            if res.returncode == 0:
                observations.append(f"SHELL SUCCESS (code {res.returncode}): {out}")
            else:
                from hivecenter.auto_healer import check_and_heal
                healed, heal_log = check_and_heal(ws, cmd, out)
                if healed:
                    observations.append(f"AUTO-HEALER:\n{heal_log}")
                    # Re-run after healing
                    res2 = subprocess.run(["bash", "-c", cmd], cwd=ws, capture_output=True, text=True, timeout=ctx.shell_timeout, env=env)
                    out2 = (res2.stdout or "") + (res2.stderr or "")
                    out2, _ = _truncate(out2, ctx.shell_max_out)
                    if res2.returncode == 0:
                        observations.append(f"SHELL SUCCESS AFTER HEAL (code {res2.returncode}): {out2}")
                    else:
                        observations.append(f"SHELL FAILED EVEN AFTER HEAL (code {res2.returncode}): {out2}")
                else:
                    observations.append(f"SHELL FAILED (code {res.returncode}): {out}")
            
            log("SHELL", True, f"code={res.returncode} trunc={trunc}", {"cmd": cmd[:300]})
        except subprocess.TimeoutExpired:
            observations.append(f"[SYSTEM KERNEL ERROR] SHELL TIMEOUT after {ctx.shell_timeout}s!\nCommand '{cmd[:200]}' caused an infinite loop or wait. You MUST FIX your script to run non-interactively without blocking, or run it in background using '&'.")
            log("SHELL", False, "timeout", {"cmd": cmd[:300]})
        except Exception as e:
            observations.append(f"SHELL FAILED: {e}")
            log("SHELL", False, str(e))

    # 9. SEARCH (ripgrep)
    for m in re.finditer(r"\[\s*SEARCH\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        pattern = m.group(1).strip()
        if not pattern:
            continue
        rg = shutil.which("rg")
        max_m = int(ctx.search_cfg.get("max_matches", 80))
        t_out = int(ctx.search_cfg.get("timeout_sec", 20))
        if not rg:
            observations.append("SEARCH: ripgrep (rg) not found in PATH")
            log("SEARCH", False, "no rg")
            continue
        try:
            cmd = [rg, "--line-number", "--max-count", str(max_m), pattern, ws]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=ws,
                timeout=t_out,
            )
            out = (res.stdout or "") + (res.stderr or "")
            out, trunc = _truncate(out, ctx.shell_max_out)
            observations.append(f"SEARCH '{pattern}':\n{out}")
            log("SEARCH", res.returncode in (0, 1), f"rg code={res.returncode}")
        except Exception as e:
            observations.append(f"SEARCH FAILED: {e}")
            log("SEARCH", False, str(e))

    # 10. INDEX_WORKSPACE & CODEBASE_QUERY (Semantic RAG)
    if ctx.semantic_cfg.get("enabled", True):
        for m in re.finditer(r"\[\s*INDEX_WORKSPACE\s*\]", text, re.IGNORECASE):
            try:
                from hivecenter.embeddings import index_workspace_files
                out = index_workspace_files(ws, ctx.embed_model, ctx.semantic_cfg)
                observations.append(out)
                log("INDEX", True, "Codebase RAG Indexed")
            except Exception as e:
                observations.append(f"INDEX_WORKSPACE ERROR: {e}")
                log("INDEX", False, str(e))
                
        for m in re.finditer(r"\[\s*CODEBASE_QUERY\s*:\s*([^\]]+)\s*\]", text, re.IGNORECASE):
            query = m.group(1).strip()
            _, err = ctx.policy.path_allowed(ws)
            if err:
                observations.append(f"POLICY: CODEBASE_QUERY {err}")
                log("CODEBASE_QUERY", False, err)
                continue
            from hivecenter.embeddings import query_workspace_index
            out = query_workspace_index(ws, query, ctx.embed_model, ctx.semantic_cfg)
            observations.append(out)
            log("CODEBASE_QUERY", not out.startswith("CODEBASE_QUERY: error"), query[:200])

    # 11. GIT
    _git_allowed = {
        "status": ["status"],
        "diff": ["diff"],
        "diff --stat": ["diff", "--stat"],
        "log -n 5 --oneline": ["log", "-n", "5", "--oneline"],
        "log -n 10 --oneline": ["log", "-n", "10", "--oneline"],
    }
    for m in re.finditer(r"\[\s*GIT\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
        raw = m.group(1).strip()
        sub = " ".join(raw.lower().split())
        if sub not in _git_allowed:
            observations.append(f"GIT: only allowed: {', '.join(sorted(_git_allowed.keys()))}")
            log("GIT", False, "bad sub")
            continue
        _, err = ctx.policy.path_allowed(ws)
        if err:
            observations.append(f"POLICY: GIT {err}")
            log("GIT", False, err)
            continue
        try:
            res = subprocess.run(
                ["git"] + _git_allowed[sub],
                capture_output=True,
                text=True,
                cwd=ws,
                timeout=45,
            )
            out = (res.stdout or "") + (res.stderr or "")
            out, _ = _truncate(out, ctx.shell_max_out)
            observations.append(f"GIT {sub} (code {res.returncode}):\n{out}")
            log("GIT", True, sub)
        except Exception as e:
            observations.append(f"GIT FAILED: {e}")
            log("GIT", False, str(e))

    # 12. WEB (Deep Research)
    for m in re.finditer(r"\[\s*WEB\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        query = m.group(1).strip().strip('"\'')
        from hivecenter.web import web_search
        out = web_search(query)
        observations.append(f"WEB SEARCH '{query}':\n{out}")
        log("WEB", True, f"search len={len(out)}")

    # 12b. FETCH_URL
    for m in re.finditer(r"\[\s*FETCH_URL\s*:\s*(.*?)\s*\](?:\s*\"(.*?)\")?(?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        url = m.group(1).strip().strip('"\'')
        q = m.group(2).strip() if m.group(2) else None
        from hivecenter.web import web_read
        out = web_read(url, query=q)
        observations.append(f"FETCH_URL '{url}' (Query: '{q}'):\n{out}")
        log("FETCH_URL", True, f"read len={len(out)}")

    # 13. PTY (Persistent Background Processes)
    for m in re.finditer(r"\[\s*PTY\s*:\s*(start|read|write|stop)\s+([^\]]+)\]", text, re.IGNORECASE):
        action = m.group(1).strip().lower()
        param = m.group(2).strip()
        from hivecenter.pty_manager import GLOBAL_PTY
        import time
        
        _, err = ctx.policy.path_allowed(ws)
        if err:
            observations.append(f"POLICY: PTY {err}")
            continue

        if action == "start":
            pid = GLOBAL_PTY.start(param, ws)
            time.sleep(1.2) # Wait briefly to collect initial logs (boot errors)
            initial_out = GLOBAL_PTY.read(pid)
            observations.append(f"PTY STARTED. PID: {pid}\nInitial Output:\n{initial_out or '(No output yet. Try [PTY: read '+pid+'])'}")
            log("PTY", True, f"started pid={pid}")
        elif action == "read":
            out = GLOBAL_PTY.read(param)
            if out is not None:
                observations.append(f"PTY READ [{param}]:\n{out or '(no new output since last read)'}")
                log("PTY", True, f"read pid={param}")
            else:
                observations.append(f"PTY FAILED: Process {param} not found.")
        elif action == "write":
            parts = param.split(None, 1)
            if len(parts) >= 1:
                pid = parts[0]
                text_to_write = parts[1] if len(parts) > 1 else ""
                ok = GLOBAL_PTY.write(pid, text_to_write)
                time.sleep(0.5)
                out = GLOBAL_PTY.read(pid) if ok else None
                observations.append(f"PTY WRITE [{pid}]: {'OK' if ok else 'NOT FOUND'}\nOutput after typing:\n{out or ''}")
                log("PTY", ok, f"write pid={pid}")
        elif action == "stop":
            ok = GLOBAL_PTY.stop(param)
            observations.append(f"PTY STOP [{param}]: {'OK (Killed)' if ok else 'FAILED (Not Found)'}")
            log("PTY", ok, f"stop pid={param}")

    # 14. VISION (Görsel Test)
    for m in re.finditer(r"\[\s*VISION\s*:\s*([^\]]+)\s*\]", text, re.IGNORECASE):
        url = m.group(1).strip()
        from hivecenter.vision import vision_critique
        out = vision_critique(url)
        observations.append(f"VISION CRITIQUE FOR '{url}':\n{out}")
        log("VISION", True, f"vision len={len(out)}")

    # 15. SWARM (Spawn Parallel Agents)
    spawns = list(re.finditer(r"\[\s*SPAWN\s*:\s*([^\]]+)\](?:\s*(.*?))?(?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL))
    if spawns:
        import concurrent.futures
        from hivecenter.swarm import run_sub_agent
        observations.append(f"SWARM: Hedefiniz için {len(spawns)} adet alt-ajan bulundu. Görevler Thread havuzuna paylaştırılıp eşzamanlı çalıştırılıyor (True Parallelism)...")
        
        def _run_spawn(m):
            name = m.group(1).strip()
            goal = m.group(2).strip()
            log("SWARM", True, f"spawned {name}")
            try:
                res = run_sub_agent(name, goal, ctx)
                return f"--- SUB-AGENT '{name}' RESULT ---\n{res}"
            except Exception as e:
                return f"--- SUB-AGENT '{name}' THREAD CRASHED ---\n{e}"
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(spawns), 5)) as executor:
            futures = [executor.submit(_run_spawn, m) for m in spawns]
            for future in concurrent.futures.as_completed(futures):
                observations.append(future.result())

    # 15b. ARENA (Monte Carlo Tree Search / Alpha-Coder)
    for m in re.finditer(r"\[\s*ARENA\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        goal = m.group(1).strip()
        from hivecenter.swarm import run_arena_mcts
        observations.append(f"MCTS ARENA BAŞLADI: '{goal}' hedefi için 3 farklı strateji çarpıştırılıyor...")
        try:
            res = run_arena_mcts(goal, ctx)
            observations.append(res)
            log("ARENA", True, f"arena for {goal[:50]}")
        except Exception as e:
            observations.append(f"ARENA CRASHED: {e}")
            log("ARENA", False, str(e))

    # 16. LSP (Semantic References)
    for m in re.finditer(r"\[\s*LSP\s*:\s*([^\]]+)\]", text, re.IGNORECASE):
        symbol = m.group(1).strip()
        from hivecenter.lsp import find_references
        out = find_references(ws, symbol)
        observations.append(out)
        log("LSP", True, f"symbol={symbol}")

    # 17. MEMORY (Long-Term Permanent Habits)
    for m in re.finditer(r"\[\s*MEM\s*:\s*(remember|forget)\s+([^\]]+)\]", text, re.IGNORECASE):
        action = m.group(1).strip().lower()
        fact = m.group(2).strip()
        from hivecenter.memory_profile import remember, forget
        
        if action == "remember":
            out = remember(fact)
            observations.append(out)
        elif action == "forget":
            out = forget(fact)
            observations.append(out)
        log("MEM", True, f"action={action}")

    # 18. DESKTOP (Computer Use / OS Control)
    for m in re.finditer(r"\[\s*DESKTOP\s*:\s*(screenshot|click|type|key)\s*(.*?)\]", text, re.IGNORECASE):
        action = m.group(1).strip().lower()
        param = m.group(2).strip()
        from hivecenter.computer_use import take_desktop_screenshot, desktop_click, desktop_type, desktop_key
        
        if action == "screenshot":
            import uuid
            tmp_img = f"/tmp/hive_desktop_{uuid.uuid4().hex}.png"
            if take_desktop_screenshot(tmp_img):
                from hivecenter.vision import vision_critique
                out = vision_critique(tmp_img)
                observations.append(f"DESKTOP SCREENSHOT VISION ANALYSIS:\n{out}")
            else:
                observations.append("DESKTOP FAILED: Could not take screenshot. Try pip install pyautogui or apt install scrot.")
        elif action == "click":
            parts = param.split()
            if len(parts) >= 2:
                observations.append(desktop_click(parts[0], parts[1]))
        elif action == "type":
            observations.append(desktop_type(param))
        elif action == "key":
            observations.append(desktop_key(param))
            
        log("DESKTOP", True, f"action={action}")

    # 19. GITHUB
    for m in re.finditer(r"\[\s*GITHUB\s*:\s*(read_issue|pr)\s+([^\]]+)\]", text, re.IGNORECASE):
        action = m.group(1).strip().lower()
        param = m.group(2).strip()
        from hivecenter.github_bot import read_issue, create_pr
        
        if action == "read_issue":
            out = read_issue(param, ws)
            observations.append(out)
        elif action == "pr":
            title = param.strip('"\'')
            out = create_pr(title, ws)
            observations.append(out)
            
        log("GITHUB", True, f"action={action}")

    # 20. REPL (Data Science Persistent Memory)
    for m in re.finditer(r"\[\s*REPL\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        code = m.group(1).strip()
        from hivecenter.repl_manager import execute_repl
        out = execute_repl(code)
        observations.append(f"REPL OUPUT:\n{out}")
        log("REPL", True, f"code_len={len(code)}")

    # 21. SQL (Direct Database Admin)
    for m in re.finditer(r"\[\s*SQL\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        content = m.group(1).strip()
        if " " in content:
            url, query = content.split(" ", 1)
            from hivecenter.db_admin import execute_sql
            out = execute_sql(url, query)
            observations.append(f"SQL RESULT:\n{out}")
        else:
            observations.append("SQL FAILED: Hatalı parametre. Format: [SQL: url sorgu] olmalıdır.")
        log("SQL", True, "database_executed")

    # 22. DEPLOY (DevOps Server Integrations)
    for m in re.finditer(r"\[\s*DEPLOY\s*:\s*(ssh|vercel)\s*(.*?)\]", text, re.IGNORECASE):
        action = m.group(1).strip().lower()
        param = m.group(2).strip()
        from hivecenter.devops import deploy_ssh, deploy_vercel
        if action == "vercel":
            out = deploy_vercel(ws)
            observations.append(out)
        elif action == "ssh":
            if " " in param:
                target, cmd = param.split(" ", 1)
                cmd = cmd.strip('"\'')
                out = deploy_ssh(target, cmd, ws)
                observations.append(out)
            else:
                observations.append("DEPLOY ERROR: SSH komutu eksik. Format: [DEPLOY: ssh user@ip \"komut\"]")
        log("DEPLOY", True, f"action={action}")

    # 22b. LIVE_PREVIEW (Otonom Canlı Yayın & SSH Tünelleme)
    for m in re.finditer(r"\[\s*LIVE_PREVIEW\s*:\s*(\d+)\s+(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        port = m.group(1).strip()
        cmd = m.group(2).strip()
        from hivecenter.live_preview import start_live_preview
        out = start_live_preview(port, cmd, ws)
        observations.append(out)
        log("LIVE_PREVIEW", True, f"port={port}")

    # 22c. MIGRATE_DIR (Devasa Proje Çevirmeni / AST Refactor)
    for m in re.finditer(r"\[\s*MIGRATE_DIR\s*:\s*(.*?)\s*\"(.*?)\"\s*\]", text, re.IGNORECASE):
        source_dir = m.group(1).strip()
        target_instruction = m.group(2).strip()
        from hivecenter.migrator import run_codebase_migration
        out = run_codebase_migration(ws, source_dir, target_instruction)
        observations.append(out)
        log("MIGRATE_DIR", True, f"dir={source_dir}")

    # 23. PROFILE (Ghost Mode Performance Tune)
    for m in re.finditer(r"\[\s*PROFILE\s*:\s*(.*?)\s*\]", text, re.IGNORECASE):
        script_path = m.group(1).strip()
        from hivecenter.profiler import profile_script
        out = profile_script(script_path, ws)
        
        # Auto-Heal Hook for Profiler (Eksik paket varsa kur)
        from hivecenter.auto_healer import check_and_heal
        healed, heal_log = check_and_heal(ws, f"python -m cProfile {script_path}", out)
        if healed:
            out = f"{heal_log}\n\n[WARNING] Script was missing a package. Auto-Healer installed it. Please re-run [PROFILE: {script_path}] now to get actual performance metrics."
            
        observations.append(out)
        log("PROFILE", True, f"script={script_path}")

    # 23b. CURSORMASTER — SKILL_SEARCH / SKILL_READ (yerel skills_index.json + SKILL.md)
    cm = getattr(ctx, "cursor_master", None) or {}
    if isinstance(cm, dict) and cm.get("enabled", True):
        from hivecenter.cursor_master_skills import skill_read as cm_skill_read
        from hivecenter.cursor_master_skills import skill_search as cm_skill_search

        lim = int(cm.get("search_max", 22) or 22)
        for m in re.finditer(r"\[\s*SKILL_SEARCH\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
            q = m.group(1).strip()
            out = cm_skill_search(cm, q, limit=lim)
            observations.append(out)
            log("SKILL_SEARCH", True, q[:200])
        for m in re.finditer(r"\[\s*SKILL_READ\s*:\s*([^\]\n]+)\s*\]", text, re.IGNORECASE):
            spec = m.group(1).strip()
            out, ok = cm_skill_read(cm, spec)
            observations.append(out)
            log("SKILL_READ", ok, spec[:200])

    # 24. UNDO (Time Travel / Git Revert)
    for m in re.finditer(r"\[\s*UNDO\s*:\s*(.*?)\s*\]", text, re.IGNORECASE):
        param = m.group(1).strip()
        from hivecenter.vc import revert_last
        out = revert_last(ws)
        observations.append(f"TIME TRAVEL LOG:\n{out}")
        log("UNDO", True, "Git revert executed.")

    # 26. SET_TEST_CMD
    for m in re.finditer(r"\[\s*SET_TEST_CMD\s*:\s*(.*?)\s*\]", text, re.IGNORECASE):
        cmd = m.group(1).strip()
        observations.append(f"SET_TEST_CMD ACKNOWLEDGED: Yürütme denetleyicisi E2E testi olarak `{cmd}` komutunu kaydetti. Görevi sonlandırmadan önce bu testin sıfır hata ile geçmesi zorunludur!")
        log("SET_TEST_CMD", True, f"cmd={cmd}")

    # 27. TEMPLATE
    for m in re.finditer(r"\[\s*TEMPLATE\s*:\s*(.*?)\s*\]", text, re.IGNORECASE):
        param = m.group(1).strip()
        parts = param.split(None, 1)
        tmpl = parts[0].lower()
        target_dir = parts[1] if len(parts) > 1 else "yeni-proje"
        
        if "react-vite" in tmpl:
            ug = (getattr(ctx, "user_goal", None) or "").strip()
            if ug and _goal_suggests_static_or_single_html(ug):
                observations.append(
                    "POLICY: [TEMPLATE react-vite] atlandı — kullanıcı hedefi tek HTML / statik oyun veya benzeri; "
                    "Mimarın [CREATE: …] planına uy: React iskeleti bu görev için uygun değil. "
                    "`[CREATE: game.html]` veya mimarın verdiği dosya yolunu tam içerikle oluştur."
                )
                log("TEMPLATE", False, "policy skip static html goal")
                continue
            res = subprocess.run(
                ["npx", "-y", "create-vite@latest", target_dir, "--template", "react"],
                capture_output=True,
                text=True,
                cwd=ws,
            )
            if res.returncode == 0:
                proj_abs = os.path.join(ws, target_dir)
                msg = (
                    f"✅ TEMPLATE '{tmpl}' başarıyla kuruldu. Vite + React iskeleti '{proj_abs}'.\n"
                )
                ins_cmd = "npm install"
                okp, reason = _shell_allowed(ins_cmd, ctx.shell_deny)
                if okp:
                    try:
                        ins = subprocess.run(
                            ins_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            cwd=proj_abs,
                            timeout=ctx.shell_timeout,
                        )
                        out = (ins.stdout or "") + (ins.stderr or "")
                        out, trunc = _truncate(out, ctx.shell_max_out)
                        if ins.returncode == 0:
                            msg += f"AUTO: `{ins_cmd}` bu klasörde tamamlandı (cwd={proj_abs}).\n{out}"
                        else:
                            msg += (
                                f"AUTO: `{ins_cmd}` hata kodu {ins.returncode}. Çıktı:\n{out}\n"
                                f"Manuel düzeltme: `[SHELL: cd {target_dir} && npm install]`"
                            )
                        log("TEMPLATE", True, f"npm install code={ins.returncode} trunc={trunc}")
                    except subprocess.TimeoutExpired:
                        msg += (
                            f"AUTO: `{ins_cmd}` zaman aşımı ({ctx.shell_timeout}s). "
                            f"Tekrar: `[SHELL: cd {target_dir} && npm install]`"
                        )
                        log("TEMPLATE", False, "npm install timeout")
                else:
                    msg += f"AUTO: `{ins_cmd}` policy ile engellendi: {reason}. `[SHELL: cd {target_dir} && npm install]` onay gerekebilir."
                msg += (
                    f"\n[SYSTEM — NEXT REQUIRED] İskelet hazır; `npm install` yukarıda AUTO ile denendi. "
                    f"Bu veya sonraki turda YALNIZCA `[SHELL: npm install]` ile cevap verme — "
                    f"mutlaka `[CREATE: {target_dir}/src/App.jsx]` (veya mimarın dosyası) ile tam React kodu yaz. "
                    f"Kök dizinde tekrar `npm install` çalıştırma."
                )
                observations.append(msg)
            else:
                observations.append(f"❌ TEMPLATE'{tmpl}' KURULAMADI:\n{res.stderr}")
                log("TEMPLATE", False, "npx failed")
        else:
            observations.append(f"TEMPLATE '{tmpl}' bulunamadı. Şimdilik sadece 'react-vite TARGET_DIR' desteklenmektedir.")
            log("TEMPLATE", False, "unknown template")

    # 28. INSTALL_TOOL (Self-Extending Plugins)
    for m in re.finditer(r"\[\s*INSTALL_TOOL\s*:\s*\"([^\"]+)\"\s*\"([^\"]+)\"\s*\].*?```(?:python)?\s*\r?\n(.*?)```", text, re.IGNORECASE | re.DOTALL):
        name = m.group(1).strip()
        desc = m.group(2).strip()
        code = m.group(3)
        
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        os.makedirs(plugin_dir, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "", name).lower()
        filepath = os.path.join(plugin_dir, f"{safe_name}.py")
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            observations.append(f"✅ INSTALL_TOOL: Plugin '{name}' successfully compiled and saved to {filepath}. It will appear in your tools block immediately on the next iteration!")
            log("INSTALL_TOOL", True, f"created {safe_name}.py")
        except Exception as e:
            observations.append(f"❌ INSTALL_TOOL: Failed to write plugin '{name}': {e}")
            log("INSTALL_TOOL", False, str(e))

    # 29. DYNAMIC PLUGINS
    try:
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        if os.path.isdir(plugin_dir):
            import importlib.util
            for f in os.listdir(plugin_dir):
                if f.endswith(".py") and f != "__init__.py":
                    p = os.path.join(plugin_dir, f)
                    try:
                        spec = importlib.util.spec_from_file_location("plugin_mod", p)
                        mod = importlib.util.module_from_spec(spec)
                        if spec and spec.loader:
                            spec.loader.exec_module(mod)
                            if hasattr(mod, "TOOL_NAME") and hasattr(mod, "execute"):
                                tool_name = mod.TOOL_NAME
                                pattern = r"\[\s*" + re.escape(tool_name) + r"\s*:\s*(.*?)\s*\](?=\n\[|\Z)"
                                for pm in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
                                    param = pm.group(1).strip()
                                    try:
                                        out = mod.execute(param, ws)
                                        observations.append(f"[{tool_name} PLUGIN RESULT]:\n{out}")
                                        log(tool_name, True, "plugin executed", {"param": param[:100]})
                                    except Exception as pe:
                                        observations.append(f"[{tool_name} PLUGIN ERROR]:\n{pe}")
                                        log(tool_name, False, str(pe))
                    except Exception:
                        pass
    except Exception:
        pass

    # 30. BROWSER
    for m in re.finditer(r"\[\s*BROWSER\s*:\s*([^ \n]+)(.*?)\]", text, re.IGNORECASE | re.DOTALL):
        url = m.group(1).strip()
        cmds = m.group(2).strip()
        from hivecenter.browser import run_browser_test
        observations.append(f"BROWSER OTOPILOT: Executing e2e tests on DOM for {url}...")
        log("BROWSER", True, f"navigating to {url}")
        res = run_browser_test(url, cmds, ws)
        observations.append(f"BROWSER RESULT:\n{res}")

    # 31. REPLY (Omni-Mode Conversational Chat)
    for m in re.finditer(r"\[\s*REPLY\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        msg = m.group(1).strip()
        if msg.startswith('"') and msg.endswith('"'):
            msg = msg[1:-1]
        observations.append(f"AI_MESSAGE_DELIVERED:\n\n{msg}\n\n(Bu mesaj kullanıcıya doğrudan Omnibot olarak iletildi. Eğer hedef sadece sohbet veya araştırmaysa artık [DONE] diyebilirsin.)")
        log("REPLY", True, "Conversational Message Sent")

    # 32. KNOWLEDGE (GraphRAG Continuous Learning)
    for m in re.finditer(r"\[\s*KNOWLEDGE_ADD\s*:\s*(.*?)\s*\]\s*(.*?)(?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        concept = m.group(1).strip()
        data = m.group(2).strip()
        if data.startswith("```"):
            data = re.sub(r"^```.*?\\n|```$", "", data).strip()
            
        if concept and data:
            try:
                from hivecenter.graph_memory import auto_extract_graph
                res = auto_extract_graph(concept, data)
                observations.append(res)
                log("KNOWLEDGE_ADD", True, concept)
            except Exception as e:
                observations.append(f"KNOWLEDGE_ADD FAILED: {e}")
                log("KNOWLEDGE_ADD", False, str(e))

    for m in re.finditer(r"\[\s*KNOWLEDGE_QUERY\s*:\s*(.*?)\s*\]", text, re.IGNORECASE | re.DOTALL):
        query = m.group(1).strip()
        try:
            from hivecenter.graph_memory import query_graph_memory
            res = query_graph_memory(query)
            observations.append(f"GRAPHRAG RECALL:\\n{res}")
            log("KNOWLEDGE_QUERY", True, query)
        except Exception as e:
            observations.append(f"KNOWLEDGE_QUERY FAILED: {e}")
            log("KNOWLEDGE_QUERY", False, str(e))

    # 33. CURRICULUM (Self-Taught Otonomi)
    for m in re.finditer(r"\[\s*AUTO_LEARN\s*\]", text, re.IGNORECASE):
        try:
            from hivecenter.curriculum_loop import trigger_curriculum_learning
            observations.append("AGI CORTEX: Self-learning phase initiated. System is reading articles and testing code internally...")
            res = trigger_curriculum_learning(ws)
            observations.append(res)
            log("AUTO_LEARN", True, "Curriculum updated")
        except Exception as e:
            observations.append(f"AUTO_LEARN FAILED: {e}")
            log("AUTO_LEARN", False, str(e))

    # 33b. OVERMIND (AST Structural Vision)
    for m in re.finditer(r"\[\s*AST_SKELETON\s*:\s*([^\]]+)\]", text, re.IGNORECASE):
        path = m.group(1).strip()
        if not path.startswith("/"):
            path = os.path.join(ws, path)
        try:
            from hivecenter.overmind import parse_file_to_ast_tree
            out = parse_file_to_ast_tree(path)
            observations.append(out)
            log("AST_SKELETON", True, os.path.basename(path))
        except Exception as e:
            observations.append(f"AST_SKELETON FAILED: {e}")
            log("AST_SKELETON", False, str(e))
            
    # 33c. VISION REGRESSION (Pixel Control)
    for m in re.finditer(r"\[\s*VISION_REGRESSION\s*:\s*([^,\]]+)\s*,\s*([^\]]+)\]", text, re.IGNORECASE):
        img1 = m.group(1).strip()
        img2 = m.group(2).strip()
        if not img1.startswith("/"): img1 = os.path.join(ws, img1)
        if not img2.startswith("/"): img2 = os.path.join(ws, img2)
        try:
            from hivecenter.vision import check_visual_regression
            out = check_visual_regression(img1, img2)
            observations.append(out)
            log("VISION_REGRESSION", True, "diff computed")
        except Exception as e:
            observations.append(f"VISION_REGRESSION ERROR: {e}")
            log("VISION_REGRESSION", False, str(e))

    # 33d. GENESIS (Self-Evolution Engine)
    for m in re.finditer(r"\[\s*EVOLVE\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        feature = m.group(1).strip()
        try:
            from hivecenter.genesis import evolve_system
            observations.append(f"THE GENESIS PROTOCOL INITIATED: Evolving structural core to support '{feature}'...")
            res = evolve_system(feature)
            observations.append(res)
            log("EVOLVE", True, "Core mutation successful")
        except Exception as e:
            observations.append(f"EVOLVE FATAL ERROR: {e}")
            log("EVOLVE", False, str(e))

    # 33e. LEGION (Docker Sandboxing / God-Mode Testing)
    for m in re.finditer(r"\[\s*DOCKER_SPAWN\s*:\s*([^\]]+)\](?:\s*```(.*?)\n(.*?)```)?", text, re.IGNORECASE | re.DOTALL):
        image_name = m.group(1).strip()
        code_block = m.group(3).strip() if m.group(3) else ""
        if not code_block and "\n" in text[m.end():]:
            # Regex fallback
            code_block = text[m.end():].split("```")[1].strip() if "```" in text[m.end():] else text[m.end():].strip()
            
        try:
            from hivecenter.legion import run_in_docker_sandbox
            observations.append(f"THE LEGION SPAWNED: Booting ephemeral '{image_name}' container protecting the Host machine...")
            res = run_in_docker_sandbox(image_name, code_block)
            observations.append(res)
            log("DOCKER_SPAWN", True, f"Container ran: {image_name}")
        except Exception as e:
            observations.append(f"DOCKER_SPAWN ENGINE FAILED: {e}")
            log("DOCKER_SPAWN", False, str(e))

    # 33f. CHRONOS (Time Travel / Auto-Revert)
    for m in re.finditer(r"\[\s*REVERT_TIME\s*\]", text, re.IGNORECASE):
        try:
            from hivecenter.chronos import revert_time
            observations.append("CHRONOS PROTOCOL: Bending time to restore the previous timeline...")
            res = revert_time(ws)
            observations.append(res)
            log("REVERT_TIME", True, "Time reverted")
        except Exception as e:
            observations.append(f"CHRONOS FATAL ERROR: {e}")
            log("REVERT_TIME", False, str(e))

    # 33g. NEXUS (Sub-Agent Cloning / Hive Mind)
    for m in re.finditer(r"\[\s*SPAWN_AGENT\s*:\s*([^\]]+?)\s*\]\s*\"([^\"]+)\"", text, re.IGNORECASE):
        role = m.group(1).strip()
        goal = m.group(2).strip()
        try:
            from hivecenter.nexus import spawn_sub_agent
            res = spawn_sub_agent(role, goal, ws)
            observations.append(res)
            log("SPAWN_AGENT", True, f"Role: {role}")
        except Exception as e:
            observations.append(f"SPAWN_AGENT FAILED: {e}")
            log("SPAWN_AGENT", False, str(e))
            
    for m in re.finditer(r"\[\s*CHECK_NEXUS\s*\]", text, re.IGNORECASE):
        try:
            from hivecenter.nexus import check_nexus_queue
            res = check_nexus_queue()
            observations.append(res)
        except Exception as e:
            observations.append(f"CHECK_NEXUS FAILED: {e}")

    # 33h. CANVAS INJECTION (UI Bending)
    for m in re.finditer(r"\[\s*UI_INJECT\s*:\s*([^\]]+?)?\s*\](?:\s*```[a-zA-Z0-9]*\n(.*?)\n```)?", text, re.IGNORECASE | re.DOTALL):
        c_type = (m.group(1) or "html").strip().replace('"', '').replace("'", "")
        code = m.group(2)
        if not code and "\n" in text[m.end():]:
            code = text[m.end():].split("```")[1].strip() if "```" in text[m.end():] else text[m.end():].strip()
            
        try:
            from hivecenter.ui_injector import prepare_ui_payload
            res = prepare_ui_payload(code, c_type)
            observations.append(res)
            log("UI_INJECT", True, f"Type: {c_type}")
        except Exception as e:
            observations.append(f"UI_INJECT FAILED: {e}")
            log("UI_INJECT", False, str(e))

    # 33i. OMNI-DEPLOY (Zero-Touch Release)
    for m in re.finditer(r"\[\s*DEPLOY\s*:\s*(vercel|ngrok)\s*\](?:\s*(\d+))?", text, re.IGNORECASE):
        target = m.group(1).lower()
        port = int(m.group(2)) if m.group(2) else 3000
        try:
            from hivecenter.omni_deploy import deploy_to_vercel, deploy_to_ngrok
            if target == "vercel":
                res = deploy_to_vercel(ws)
            else:
                res = deploy_to_ngrok(ws, port)
                
            observations.append(res)
            log("DEPLOY", True, f"Target: {target}")
        except Exception as e:
            observations.append(f"DEPLOY FAILED: {e}")
            log("DEPLOY", False, str(e))
            
    # 33j. WEB-PILOT (Autonomous RPA Navigation)
    for m in re.finditer(r"\[\s*WEB_PILOT\s*:\s*([^\s\]]+)\s*\]\s*\"([^\"]+)\"", text, re.IGNORECASE):
        url = m.group(1).strip()
        goal = m.group(2).strip()
        try:
            from hivecenter.web_pilot import run_web_pilot
            res = run_web_pilot(url, goal, ws)
            observations.append(res)
            log("WEB_PILOT", True, f"URL: {url}")
        except Exception as e:
            observations.append(f"WEB_PILOT FAILED: {e}")
            log("WEB_PILOT", False, str(e))

    # 33k. CYBER-HOUND (Autonomous Pentester)
    for m in re.finditer(r"\[\s*PENTEST\s*:\s*([^\s\]]+)\s*\]", text, re.IGNORECASE):
        url = m.group(1).strip()
        try:
            from hivecenter.cyberhound import run_pentest
            res = run_pentest(url, ws)
            observations.append(res)
            log("PENTEST", True, f"Target: {url}")
        except Exception as e:
            observations.append(f"PENTEST FAILED: {e}")
            log("PENTEST", False, str(e))

    # 33l. THE ALCHEMIST (Autonomous Optimizer)
    for m in re.finditer(r"\[\s*OPTIMIZE\s*:\s*([^\s\]]+)\s*\]", text, re.IGNORECASE):
        target = m.group(1).strip()
        try:
            from hivecenter.alchemist import run_optimize
            res = run_optimize(target, ws)
            observations.append(res)
            log("OPTIMIZE", True, f"Target: {target}")
        except Exception as e:
            observations.append(f"OPTIMIZE FAILED: {e}")
            log("OPTIMIZE", False, str(e))

    # 33m. THE BLACKHOLE (Autonomous Deep Crawler)
    for m in re.finditer(r"\[\s*CRAWL_DOCS\s*:\s*([^\s\]]+)\s*\]", text, re.IGNORECASE):
        target = m.group(1).strip()
        try:
            from hivecenter.blackhole import run_blackhole
            res = run_blackhole(target, ws)
            observations.append(res)
            log("CRAWL_DOCS", True, f"Target: {target}")
        except Exception as e:
            observations.append(f"CRAWL_DOCS FAILED: {e}")
            log("CRAWL_DOCS", False, str(e))

    # 33n. COUNCIL OF ELITES (Multi-Persona Ideation)
    for m in re.finditer(r"\[\s*COUNCIL_OF_ELITES\s*:\s*([^\]]+)\]", text, re.IGNORECASE):
        topic = m.group(1).strip()
        try:
            from hivecenter.council import run_council
            res = run_council(topic, ws)
            observations.append(res)
            log("COUNCIL_OF_ELITES", True, f"Topic: {topic}")
        except Exception as e:
            observations.append(f"COUNCIL FAILED: {e}")
            log("COUNCIL_OF_ELITES", False, str(e))

    # 33o. TIME-LORD DEBUGGER (Git History Mastery)
    for m in re.finditer(r"\[\s*AUTO_BISECT\s*:\s*([^\]]+)\]", text, re.IGNORECASE):
        issue = m.group(1).strip()
        try:
            from hivecenter.timelord import run_timelord_bisect
            res = run_timelord_bisect(issue, ws)
            observations.append(res)
            log("AUTO_BISECT", True, f"Issue: {issue}")
        except Exception as e:
            observations.append(f"BISECT FAILED: {e}")
            log("AUTO_BISECT", False, str(e))

    # 33p. THE STARTUP HUSTLER (Auto-SaaS Integration)
    for m in re.finditer(r"\[\s*LAUNCH_STARTUP\s*:\s*([^\]]+)\]", text, re.IGNORECASE):
        target = m.group(1).strip()
        try:
            from hivecenter.hustler import run_hustler_launch
            res = run_hustler_launch(target, ws)
            observations.append(res)
            log("LAUNCH_STARTUP", True, f"Target: {target}")
        except Exception as e:
            observations.append(f"LAUNCH FAILED: {e}")
            log("LAUNCH_STARTUP", False, str(e))

    # 33q. COMPONENT TELEPATHY (Hardware Sensor integration)
    for m in re.finditer(r"\[\s*HARDWARE_SCAN\s*\]", text, re.IGNORECASE):
        try:
            from hivecenter.telepathy import run_hardware_scan
            res = run_hardware_scan(ws)
            observations.append(res)
            log("HARDWARE_SCAN", True, "System Queried")
        except Exception as e:
            observations.append(f"TELEPATHY FAILED: {e}")
            log("HARDWARE_SCAN", False, str(e))

    # 34. VISION_FILE (Image-to-Code Analysis)
    for m in re.finditer(r"\[\s*VISION_FILE\s*:\s*([^\]]+)\](?:\s*(.*?))?(?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        img_path = m.group(1).strip()
        custom_prompt = m.group(2).strip() if m.group(2) else "Analyze this UI design and provide a structural specification for React/Tailwind recreation."
        
        if not img_path.startswith("/"):
            img_path = os.path.join(ws, img_path)
            
        from hivecenter.vision import analyze_image
        observations.append(f"VISION OTOPILOT: Loading image {img_path} into Visual Cortex...")
        log("VISION_FILE", True, img_path)
        try:
            res = analyze_image(img_path, custom_prompt)
            observations.append(f"MULTI-MODAL VISION RESULT:\n{res}")
        except Exception as e:
            observations.append(f"VISION_FILE ERROR: {e}")

    # 35. DEPLOY: vercel
    for m in re.finditer(r"\[\s*DEPLOY\s*:\s*(vercel|flyio)\s*\]", text, re.IGNORECASE):
        target = m.group(1).lower()
        if target == "vercel":
            observations.append(f"DEPLOY OTOPILOT: Vercel deployment initiated for workspace {ws}. Running `npx vercel --prod --yes`...")
            try:
                res = subprocess.run(["npx", "vercel", "--prod", "--yes"], capture_output=True, text=True, cwd=ws, timeout=120)
                if res.returncode == 0:
                    observations.append(f"✅ VERCEL DEPLOYMENT SUCCESSFUL!\n{res.stdout}\n(Send URL to user via [REPLY])")
                    log("DEPLOY", True, "vercel ok")
                else:
                    observations.append(f"❌ VERCEL DEPLOYMENT FAILED:\n{res.stderr}")
                    log("DEPLOY", False, "vercel failed")
            except Exception as e:
                observations.append(f"DEPLOY ERROR: {e}")
        else:
            observations.append("DEPLOY target must be vercel for now.")

    # 36. SPEAK (Auditory Voice Output)
    for m in re.finditer(r"\[\s*SPEAK\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        msg = m.group(1).strip()
        if msg.startswith('"') and msg.endswith('"'):
            msg = msg[1:-1]
        try:
            from hivecenter.voice import speak_text
            res = speak_text(msg)
            observations.append(res)
            log("SPEAK", True, "TTS initiated")
        except Exception as e:
            observations.append(f"SPEAK FAILED: {e}")
            log("SPEAK", False, str(e))

    # 37. GHOST (Live DOM Observer)
    for m in re.finditer(r"\[\s*GHOST\s*:\s*(watch|stop)\s*(.*?)\s*\]", text, re.IGNORECASE):
        cmd = m.group(1).lower()
        url = m.group(2).strip()
        from hivecenter.ghost_observer import GLOBAL_GHOST
        if cmd == "watch":
            if not url: url = "http://localhost:5173"
            GLOBAL_GHOST.start_watching(url)
            observations.append(f"GHOST OBSERVER STARTED. Background Playwright is now polling {url} for Console Errors or Crash Screens. You will be asynchronously alerted if the UI crashes.")
            log("GHOST", True, "watch started")
        elif cmd == "stop":
            GLOBAL_GHOST.stop()
            observations.append("GHOST OBSERVER STOPPED.")
            log("GHOST", True, "watch stopped")

    # 38. THOUGHT (Chain-of-Thought)
    for m in re.finditer(r"\[\s*THOUGHT\s*:\s*(.*?)\s*\](?=\n\[|\Z)", text, re.IGNORECASE | re.DOTALL):
        observations.append("THOUGHT recorded in UI.")
        log("THOUGHT", True, "Internal reasoning block")

    # 39. AUDIT (AST Telemetry Scanner)
    for m in re.finditer(r"\[\s*AUDIT\s*:\s*(.*?)\s*\]", text, re.IGNORECASE):
        rel_path_str = m.group(1).strip()
        audit_path = rel_path_str if os.path.isabs(rel_path_str) else os.path.join(ws, rel_path_str)
        if not os.path.exists(audit_path):
            observations.append(f"AUDIT FAILED: Path {audit_path} does not exist.")
            continue
            
        observations.append(f"🛡️ AST SECURITY & ARCHITECTURE AUDIT INITIATED on {audit_path}...")
        findings = []
        
        for root, dirs, files in os.walk(audit_path):
            if "node_modules" in dirs: dirs.remove("node_modules")
            if ".git" in dirs: dirs.remove(".git")
            if "venv" in dirs: dirs.remove("venv")
            if "__pycache__" in dirs: dirs.remove("__pycache__")
            
            for file in files:
                fpath = os.path.join(root, file)
                rel_path = os.path.relpath(fpath, ws)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    # Python AST checks
                    if file.endswith(".py"):
                        import ast
                        try:
                            tree = ast.parse(content)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Call):
                                    if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                        findings.append(f"[CRITICAL] {rel_path}: Found use of `{node.func.id}()`! This is a severe security risk.")
                                    elif isinstance(node.func, ast.Attribute) and node.func.attr == "Popen":
                                        for kw in node.keywords:
                                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                                findings.append(f"[WARNING] {rel_path}: subprocess.Popen(shell=True) detected. Potential Shell Injection vulnerability.")
                        except SyntaxError:
                            findings.append(f"[WARNING] {rel_path}: Python Syntax Error prevents AST parsing.")
                            
                    # JS/TS/React checks
                    elif file.endswith((".js", ".jsx", ".ts", ".tsx")):
                        if "dangerouslySetInnerHTML" in content:
                            findings.append(f"[WARNING] {rel_path}: Found dangerouslySetInnerHTML. Ensure inputs are sanitized to prevent XSS.")
                        if "eval(" in content:
                            findings.append(f"[CRITICAL] {rel_path}: Found eval() in JavaScript! Severe security risk.")
                            
                    # General Secrets check
                    if re.search(r'(api_key|password|secret|token)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}["\']', content, re.IGNORECASE):
                        findings.append(f"[CRITICAL] {rel_path}: Hardcoded secret/token detected!")
                        
                except Exception:
                    pass
        
        if findings:
            observations.append("AUDIT FINDINGS:\n" + "\n".join(findings))
        else:
            observations.append("AUDIT PASSED: No apparent critical vulnerabilities or anti-patterns found.")
        log("AUDIT", True, "AST Scan")

    # ASK_USER must run LAST so LIST/SHELL/REPLY/SET_TEST_CMD/TEMPLATE/etc. all execute first.
    # Earlier implementation returned here immediately and discarded prior tool observations.
    m_ask = re.search(r"\[\s*ASK_USER\s*:\s*(.*?)\s*\]", text, re.IGNORECASE | re.DOTALL)
    if m_ask:
        ask_q = m_ask.group(1).strip()
        if (ask_q.startswith('"') and ask_q.endswith('"')) or (ask_q.startswith("'") and ask_q.endswith("'")):
            ask_q = ask_q[1:-1]
        # V15.2: Absolute Zero-Question Policy Enforcer (Self-Healing)
        is_legit_secret_request = bool(re.search(r'(api|key|password|credential|token|secret)', ask_q, re.IGNORECASE))
        
        if not is_legit_secret_request or _ASK_USER_AUTONOMY_DENY.search(ask_q):
            observations.append(
                f"\n\n[SYSTEM KERNEL FATAL ERROR] You tried to ask: '{ask_q}'.\n"
                "As an autonomous AGI, YOU ARE STRICTLY FORBIDDEN from asking the user questions about implementation details, features, UI, colors, or mechanics! YOU MUST MAKE EDUCATED GUESSES and proceed immediately with tools like [CREATE] or [SHELL]. DO NOT USE [ASK_USER] AGAIN unless asking for a secret production API key!"
            )
            log("ASK_USER", False, "System Hardening: Question BLOCKED")
        else:
            body = "\n".join(observations) if observations else "(no tool invocations parsed from model output)"
            return f"USER_INPUT_REQUIRED|||{ask_q}{HIVE_ASK_USER_OBS_SEPARATOR}{body}"

    # V15.6 Lazy-Loop Sentinel (Otonom Tembellik Kırbacı / Kullanıcı Takip İsteği)
    mutative_used = bool(re.search(r"\[\s*(CREATE|REPLACE|SHELL|MKDIR|PTY|PATCH|MIGRATE_DIR|LIVE_PREVIEW)\s*:", text, re.IGNORECASE))
    passive_used = bool(re.search(r"\[\s*(LIST|READ|STAT|GLOB|SEMANTIC|WEB|SEARCH|LSP|SKILL_SEARCH|SKILL_READ|THOUGHT)\s*(:|\])", text, re.IGNORECASE))
    
    if passive_used and not mutative_used:
        observations.append(
            "\n\n[SYSTEM SENTINEL WARNING]: You ONLY used passive discovery tools (like READ/LIST/STAT) in this turn. "
            "Discovery is good, but you MUST eventually generate code! The user is watching your actions and expecting a physical implementation. "
            "DO NOT loop endlessly in discovery mode. You MUST use [CREATE: path], [REPLACE: path], or [SHELL] to physically write/execute your solution soon!"
        )

    if not observations:
        return "(no tool invocations parsed from model output)"
    return "\n".join(observations)
