import os
from typing import List, Optional, Tuple


def _real(p: str) -> str:
    try:
        return os.path.realpath(p)
    except OSError:
        return os.path.abspath(p)


class PolicyContext:
    """Allowlist + yasaklı alt dizge kontrolü (symlink çözülmüş gerçek yol üzerinden)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.roots: List[str] = [_real(r) for r in cfg.get("allowed_roots", [])]
        self.forbidden = [x.lower() for x in cfg.get("forbidden_path_substrings", [])]

    def path_allowed(self, abs_path: str) -> Tuple[bool, str]:
        rp = _real(abs_path)
        low = rp.lower()
        god_mode = self.cfg.get("god_mode", False)
        for fb in self.forbidden:
            if fb and fb in low:
                return False, f"policy: forbidden path pattern matched ({fb!r})"
        
        if god_mode:
            return True, ""
            
        for root in self.roots:
            if root and (rp == root or rp.startswith(root + os.sep)):
                return True, ""
        return False, "policy: path outside allowed_roots"

    def resolve_safe(self, workspace_root: str, rel: str) -> Tuple[Optional[str], Optional[str]]:
        """rel workspace'e göre birleştirilir; kaçak (..) realpath ile yakalanır. God mode ise absolute path kabul edilir."""
        ws = _real(workspace_root)
        god_mode = self.cfg.get("god_mode", False)
        if god_mode and os.path.isabs(os.path.expanduser(rel)):
            joined = os.path.normpath(os.path.expanduser(rel))
        else:
            joined = os.path.normpath(os.path.join(ws, rel.lstrip("/\\")))
        rp = _real(joined)
        ok, reason = self.path_allowed(rp)
        if not ok:
            return None, reason
        return rp, None
