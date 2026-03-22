import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hivecenter.prompts import architect_user_prompt, coder_user_prompt


class TestArchitectPrompt(unittest.TestCase):
    def test_includes_agent_state_when_provided(self):
        p = architect_user_prompt("g", "obs", 1, None, None, "", "prior line")
        self.assertIn("ROLLING AGENT STATE", p)
        self.assertIn("prior line", p)

    def test_omits_agent_state_when_empty(self):
        p = architect_user_prompt("g", "obs", 1, None, None, "", None)
        self.assertNotIn("ROLLING AGENT STATE", p)

    def test_full_mission_brief_in_architect_prompt(self):
        p = architect_user_prompt("build a feature", "obs", 1, None, None, "", None)
        self.assertIn("FULL MISSION", p)

    def test_full_mission_brief_in_coder_prompt(self):
        p = coder_user_prompt("plan", "goal", None, "/tmp/ws")
        self.assertIn("FULL MISSION", p)


if __name__ == "__main__":
    unittest.main()
