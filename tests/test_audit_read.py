import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.audit_read import read_recent_audit_entries


class TestAuditRead(unittest.TestCase):
    def test_empty_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "missing.ndjson")
            self.assertEqual(read_recent_audit_entries(p, 10), [])

    def test_returns_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.ndjson")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"n": 1}) + "\n")
                f.write(json.dumps({"n": 2}) + "\n")
                f.write(json.dumps({"n": 3}) + "\n")
            out = read_recent_audit_entries(p, 2)
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0].get("n"), 3)
            self.assertEqual(out[1].get("n"), 2)

    def test_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.ndjson")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"ok": True}) + "\n")
                f.write("not json\n")
                f.write(json.dumps({"ok": False}) + "\n")
            out = read_recent_audit_entries(p, 10)
            self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
