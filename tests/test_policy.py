import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.policy import PolicyContext


class TestPolicy(unittest.TestCase):
    def test_resolve_safe_blocks_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "allowed_roots": [tmp],
                "forbidden_path_substrings": [".ssh", "/etc/"],
            }
            p = PolicyContext(cfg)
            # workspace/tmp/foo + ".." -> /tmp (parent), outside allowed root
            path, err = p.resolve_safe(tmp, "..")
            self.assertIsNone(path)
            self.assertIsNotNone(err)

    def test_resolve_safe_allows_inside(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"allowed_roots": [tmp], "forbidden_path_substrings": []}
            p = PolicyContext(cfg)
            path, err = p.resolve_safe(tmp, "sub/file.txt")
            self.assertIsNotNone(path)
            self.assertIsNone(err)
            self.assertTrue(path.startswith(os.path.realpath(tmp)))


if __name__ == "__main__":
    unittest.main()
