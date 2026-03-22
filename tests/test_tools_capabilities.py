import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.tools import _parse_read_spec


class TestParseReadSpec(unittest.TestCase):
    def test_line_range(self):
        p, a, b = _parse_read_spec("src/a.py#L10-L120")
        self.assertEqual(p, "src/a.py")
        self.assertEqual(a, 10)
        self.assertEqual(b, 120)

    def test_plain_path(self):
        p, a, b = _parse_read_spec("README.md")
        self.assertEqual(p, "README.md")
        self.assertIsNone(a)
        self.assertIsNone(b)

    def test_invalid_range_falls_back(self):
        p, a, b = _parse_read_spec("x#L5-L3")
        self.assertIn("#L", p)
        self.assertIsNone(a)


if __name__ == "__main__":
    unittest.main()
