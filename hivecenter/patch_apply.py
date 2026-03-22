"""Unified diff uygulama: önce git apply, yoksa patch -p1 (policy ile uyumlu)."""
import os
import re
import shutil
import subprocess
import uuid
from typing import Tuple


def validate_diff_paths(diff_body: str) -> Tuple[bool, str]:
    if len(diff_body) > 900_000:
        return False, "diff too large (>900KB)"
    for line in diff_body.splitlines():
        if line.startswith("---") or line.startswith("+++") or line.startswith("diff --git"):
            if ".." in line:
                return False, "diff path lines must not contain '..'"
            if re.search(r"(?i)(/etc/passwd|\.ssh)", line):
                return False, "suspicious path in diff header"
    return True, ""


def apply_search_replace(workspace_root: str, hint_path: str, search_body: str, replace_body: str) -> Tuple[bool, str]:
    """Aider-style SEARCH/REPLACE algorithm."""
    path = os.path.join(workspace_root, hint_path)
    
    if not os.path.isfile(path):
        return False, f"File not found for replace: {hint_path}"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalize line endings
    search_body = search_body.replace("\r\n", "\n")
    replace_body = replace_body.replace("\r\n", "\n")
    content_nl = content.replace("\r\n", "\n")

    def _write_with_ast_check(p: str, c: str) -> Tuple[bool, str]:
        if p.endswith(".py"):
            try:
                import ast
                ast.parse(c)
            except SyntaxError as e:
                return False, f"AST Linter Blocked: The resulting code has a SyntaxError on line {e.lineno}: {e.msg}\\nPlease fix your REPLACE block."
                
        try:
            from hivecenter.chronos import take_snapshot
            take_snapshot(workspace_root, p)
        except Exception:
            pass
            
        with open(p, "w", encoding="utf-8") as file_obj:
            file_obj.write(c)
        return True, "Search/Replace applied successfully."

    # If exact match
    if search_body in content_nl:
        count = content_nl.count(search_body)
        if count > 1:
            return False, f"SEARCH block found {count} times in file. Needs to be more specific to uniquely identify the location."
        new_content = content_nl.replace(search_body, replace_body)
        return _write_with_ast_check(path, new_content)

    # Try matching without leading/trailing empty lines
    search_stripped = search_body.strip("\\n")
    if search_stripped in content_nl:
        count = content_nl.count(search_stripped)
        if count > 1:
            return False, "SEARCH block found multiple times when stripped. Needs more uniquely identifying lines."
        new_content = content_nl.replace(search_stripped, replace_body.strip("\\n"))
        return _write_with_ast_check(path, new_content)

    return False, "SEARCH block not found exactly in file. Check for typos or stale line references. Remember to include enough unique context lines in your SEARCH block."




def apply_unified_diff(workspace_root: str, diff_body: str) -> Tuple[bool, str]:
    ok, msg = validate_diff_paths(diff_body)
    if not ok:
        return False, msg
    patch_dir = os.path.join(workspace_root, ".hive", "patches")
    os.makedirs(patch_dir, exist_ok=True)
    fn = os.path.join(patch_dir, f"apply_{uuid.uuid4().hex}.diff")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(diff_body)

    if os.path.isdir(os.path.join(workspace_root, ".git")):
        chk = subprocess.run(
            ["git", "apply", "--check", fn],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if chk.returncode != 0:
            err = (chk.stderr or chk.stdout or "").strip()
            return False, f"git apply --check failed: {err[:4000]}"
        ap = subprocess.run(
            ["git", "apply", fn],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if ap.returncode != 0:
            err = (ap.stderr or ap.stdout or "").strip()
            return False, f"git apply failed: {err[:4000]}"
        return True, "Applied with git apply."

    if not shutil.which("patch"):
        return False, "Neither git repo nor `patch` CLI found; cannot apply diff."

    dry = subprocess.run(
        ["patch", "-p1", "--dry-run", "-i", fn],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if dry.returncode != 0:
        err = (dry.stderr or dry.stdout or "").strip()
        return False, f"patch dry-run failed: {err[:4000]}"
    ap = subprocess.run(
        ["patch", "-p1", "-i", fn],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if ap.returncode != 0:
        err = (ap.stderr or ap.stdout or "").strip()
        return False, f"patch failed: {err[:4000]}"
    return True, "Applied with patch -p1."
