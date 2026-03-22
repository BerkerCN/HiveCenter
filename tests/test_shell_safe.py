import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.shell_safe import is_hard_denied


class TestShellSafe(unittest.TestCase):
    def test_builtin_rm_rf_root(self):
        d, _ = is_hard_denied("rm -rf /", [])
        self.assertTrue(d)

    def test_extra_pattern(self):
        d, _ = is_hard_denied("something badtool x", ["badtool"])
        self.assertTrue(d)

    def test_ok(self):
        d, _ = is_hard_denied("ls -la", [])
        self.assertFalse(d)


if __name__ == "__main__":
    unittest.main()
