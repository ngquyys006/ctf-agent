"""End-to-end integration tests.

Runs one complete solve through the four memory modules and the tool
runner, and verifies the workflow does not depend on the process working
directory (spec sections 30, 34, 42, 43).
"""

import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

import config
from memory import save_experience, save_knowledge, search, update_knowledge
from tests import _util
from tools import runner

_STATE = {}


def setUpModule():
    _STATE.update(_util.snapshot())


def tearDownModule():
    _util.restore(_STATE)


class CompleteScenarioTests(unittest.TestCase):
    """The example complete scenario, end to end (spec section 43)."""

    def setUp(self):
        self.addCleanup(config.KNOWLEDGE_DIR.joinpath("scenario.md").unlink, missing_ok=True)
        self.addCleanup(config.EXPERIENCE_DIR.joinpath("lab-999.md").unlink, missing_ok=True)
        self.addCleanup(config.TOOLS_SCRIPTS_DIR.joinpath("reflect_scan.py").unlink, missing_ok=True)
        self.addCleanup(runner.remove, "scenario_tmp")
        save_knowledge.save_knowledge("scenario", "## Method\n1. Find the source.\n",
                                      tags="scenario-xss", technique="xss")
        save_experience.save_experience("lab-125", "DOM XSS via innerHTML",
                                        "## Challenge Summary\nReflected through innerHTML.",
                                        tags="innerHTML", technique="xss")

    def test_complete_scenario(self):
        # --- Memory needed? yes -> search Knowledge and Experience ---
        knowledge = search.search("scenario-xss", memory_type="knowledge")
        self.assertEqual([r["path"] for r in knowledge], ["knowledge/scenario.md"])
        experience = search.search("innerHTML", memory_type="experience")
        self.assertEqual([r["path"] for r in experience], ["experiences/lab-125.md"])
        self.assertIn("Find the source", search.read("scenario")["content"])

        # --- Existing tools insufficient -> create a tool, run it, keep it ---
        tool = runner.create("reflect_scan",
                             '"""Scan a URL for reflection.\n\nCategory: web\n'
                             'Arguments: url\n"""\nimport sys\n'
                             "url = sys.argv[1] if len(sys.argv) > 1 else ''\n"
                             'print("reflected:", url)\n')
        self.assertIsNotNone(tool)
        result = runner.run("reflect_scan", ["http://target.local/search?q=<script>"])
        self.assertTrue(result["success"])
        self.assertIn("reflected:", result["stdout"])
        self.assertIn("reflect_scan", [t["name"] for t in runner.list_tools()])

        # --- A failing tool is information, not a reason to stop ---
        runner.create("scenario_tmp", '"""Probe."""\nimport sys\n'
                                      'print("failed", file=sys.stderr)\nsys.exit(2)\n')
        failed = runner.run("scenario_tmp")
        self.assertFalse(failed["success"])
        self.assertEqual(failed["exit_code"], 2)
        self.assertIn("failed", failed["stderr"])

        # --- Solved? yes -> record the challenge ---
        saved = save_experience.save_experience(
            "lab-999", "DOM XSS via innerHTML in search page",
            "## Challenge Summary\nSearch page reflects the q parameter.\n\n"
            "## Failed Approaches\n- The initial failing probe (exit code 2).\n",
            tags=["dom-xss", "innerHTML"], technique="xss")
        self.assertEqual(saved["path"], "experiences/lab-999.md")
        found = {r["path"] for r in search.search("innerHTML", memory_type="experience")}
        self.assertEqual(found, {"experiences/lab-125.md", "experiences/lab-999.md"})

        # --- Generalizable lesson? yes -> update the existing Knowledge ---
        current = search.read("scenario")["content"]
        updated = update_knowledge.update_knowledge(
            "scenario", current + "\n## Lessons\n- innerHTML is a dangerous sink.\n",
            tags="scenario-xss", technique="xss")
        self.assertEqual(updated["path"], "knowledge/scenario.md")
        self.assertIn("Lessons", search.read("scenario")["content"])
        self.assertEqual(len(list(config.KNOWLEDGE_DIR.glob("scenario*.md"))), 1)

    def test_no_operation_loads_all_memory(self):
        for module in (search, save_knowledge, update_knowledge, save_experience):
            for forbidden in ("load_all_knowledge", "load_all_experiences"):
                self.assertNotIn(forbidden, dir(module))


class WorkingDirectoryTests(unittest.TestCase):
    """The workflow works whatever the process working directory (section 34)."""

    def test_full_workflow_from_a_foreign_directory(self):
        script = textwrap.dedent(
            """
            import sys

            sys.path.insert(0, sys.argv[1])

            import config
            from memory import save_experience, save_knowledge, search, update_knowledge
            from tools import runner

            assert save_knowledge.save_knowledge("cwd_topic", "Body.", tags="cwd")["path"] \\
                == "knowledge/cwd_topic.md"
            assert [r["path"] for r in search.search("cwd", memory_type="knowledge")] \\
                == ["knowledge/cwd_topic.md"]
            assert update_knowledge.update_knowledge("cwd_topic", "Body. More.", tags="cwd")
            assert "More." in search.read("cwd_topic")["content"]
            assert save_experience.save_experience("cwd-exp", "Cwd", "Body.")["path"] \\
                == "experiences/cwd-exp.md"
            assert runner.create("cwd_tool", '\"\"\"Tool.\"\"\"\\nprint("tool")\\n')
            assert runner.run("cwd_tool")["success"]
            assert runner.remove("cwd_tool")
            print("OK")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script, str(config.BASE_DIR)],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)
        for path in (
            config.KNOWLEDGE_DIR / "cwd_topic.md",
            config.EXPERIENCE_DIR / "cwd-exp.md",
        ):
            self.addCleanup(path.unlink, missing_ok=True)
        search.rebuild()


if __name__ == "__main__":
    unittest.main()