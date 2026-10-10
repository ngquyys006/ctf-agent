"""System prompt tests (spec sections 6, 29, 31, 37).

prompts/system.md must define how Antigravity operates: the
complete section 30 solving loop as the section 29 instructions,
in order.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

import config


class SystemPromptTests(unittest.TestCase):
    """prompts/system.md defines how Antigravity operates (section 29)."""

    @classmethod
    def setUpClass(cls):
        cls.prompt = (config.PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        cls.lowered = cls.prompt.lower()

    def test_all_nineteen_instructions_appear_in_loop_order(self):
        phrases = [
            "observe the challenge",                              # 1
            "acknowledge your current understanding",             # 2
            "decide whether memory is useful",                    # 3
            "search knowledge when general knowledge is needed",  # 4
            "search experience when previous concrete attempts may help",  # 5
            "do not load all memory",                             # 6
            "analyze retrieved memory critically",                # 7
            "form a hypothesis",                                  # 8
            "select an appropriate tool",                         # 9
            "execute through the runner",                         # 10
            "analyze the result",                                 # 11
            "update the hypothesis when necessary",               # 12
            "iterate when not solved",                            # 13
            "create a tool script only when necessary",           # 14
            "test created tool scripts",                          # 15
            "keep useful scripts and remove the rest",            # 16
            "verify the final result before declaring success",   # 17
            "save the challenge experience",                      # 18
            "extract reusable knowledge only when genuinely generalizable",  # 19
        ]
        positions = []
        for phrase in phrases:
            position = self.lowered.find(phrase)
            self.assertGreaterEqual(position, 0, phrase)
            positions.append(position)
        # the instructions appear in the section 30 loop order
        self.assertEqual(positions, sorted(positions))

    def test_acknowledge_example_is_present(self):
        for line in ("Observed:", "Acknowledge:", "Possible DOM XSS"):
            self.assertIn(line, self.prompt)

    def test_memory_decision_cases_are_present(self):
        for phrase in ("Known general technique",
                       "Strong similarity to a previous challenge",
                       "Difficult challenge", "Both are useful"):
            self.assertIn(phrase, self.prompt)

    def test_important_instruction_is_verbatim(self):
        # unwrap Markdown blockquote markers and line breaks
        unwrapped = " ".join(
            line.lstrip("> ").strip() for line in self.prompt.splitlines()
        )
        collapsed = " ".join(unwrapped.split())
        self.assertIn(
            "Never assume that a retrieved Experience is correct for the current "
            "challenge. Treat it as evidence, not truth.",
            collapsed,
        )

    def test_verification_guidance_is_present(self):
        self.assertIn("Tool success and challenge success are different things",
                      self.prompt)
        self.assertIn("not as a reason to stop", self.prompt)

    def test_boundaries_forbid_a_second_reasoning_engine(self):
        self.assertIn("do not create another reasoning engine", self.lowered)


if __name__ == "__main__":
    unittest.main()
