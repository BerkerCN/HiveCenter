import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.model_io import strip_reasoning_tags


class TestStrip(unittest.TestCase):
    def test_strip_think_xml(self):
        t = "Hello<think>ignore\n</think>\n[LIST: ./]"
        out = strip_reasoning_tags(t, True)
        self.assertIn("[LIST:", out)
        self.assertNotIn("think", out.lower())

    def test_disabled(self):
        t = "<think>x</think>"
        out = strip_reasoning_tags(t, False)
        self.assertIn("think", out.lower())


if __name__ == "__main__":
    unittest.main()
