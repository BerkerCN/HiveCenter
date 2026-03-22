import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.patch_apply import validate_diff_paths


class TestPatch(unittest.TestCase):
    def test_rejects_parent_in_diff(self):
        ok, msg = validate_diff_paths("--- a/../../etc/passwd\n+++ b/foo\n")
        self.assertFalse(ok)

    def test_accepts_simple(self):
        ok, msg = validate_diff_paths(
            "--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1 @@\n+x\n"
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
