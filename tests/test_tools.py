"""Tool script tests: create, list, run, and remove.

Covers the docstring metadata convention, the script lifecycle, execution
results, and the safety boundaries (spec sections 23-28, 41, 47).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

import config
from tests import _util
from tools import runner

_STATE = {}


def setUpModule():
    _STATE.update(_util.snapshot())


def tearDownModule():
    _util.restore(_STATE)


class ToolTestCase(unittest.TestCase):
    """Per-test cleanup for the scripts a test creates."""

    def _track(self, name):
        self.addCleanup(config.TOOLS_SCRIPTS_DIR.joinpath(f"{name}.py").unlink, missing_ok=True)


class CatalogTests(ToolTestCase):
    """Describing the available scripts (spec section 23)."""

    def test_create_reads_docstring_metadata(self):
        self._track("http_probe")
        record = runner.create("http_probe",
                               '"""Perform HTTP probing.\n\nCategory: web\n'
                               'Arguments: url, timeout\n"""\nprint("probe")\n')
        self.assertIsNotNone(record)
        self.assertEqual(record["description"], "Perform HTTP probing.")
        self.assertEqual(record["category"], "web")
        self.assertEqual(record["arguments"], ["url", "timeout"])
        self.assertEqual(record["script_path"], "tools/scripts/http_probe.py")

    def test_list_and_get(self):
        self._track("listed_tool")
        runner.create("listed_tool", '"""A listed tool."""\nprint("x")\n')
        self._track("_helper")
        config.TOOLS_SCRIPTS_DIR.joinpath("_helper.py").write_text('"""Helper."""\n', encoding="utf-8")

        names = [tool["name"] for tool in runner.list_tools()]
        self.assertIn("listed_tool", names)
        self.assertNotIn("_helper", names)  # underscore files are not tools
        self.assertEqual(names, sorted(names))
        self.assertIsNotNone(runner.get("listed_tool"))
        self.assertIsNone(runner.get("never_created"))

    def test_create_refuses_invalid_input(self):
        self._track("kept_safe")
        self.assertIsNone(runner.create("../escape", '"""Escape."""\n'))
        self.assertIsNone(runner.create("bad name!", '"""Bad name."""\n'))
        self.assertIsNone(runner.create("kept_safe", ""))
        self.assertIsNone(runner.create("kept_safe", '"""Broken."""\nthis is not python(\n'))
        self.assertIsNotNone(runner.create("kept_safe", '"""Safe."""\nprint("x")\n'))
        # an existing script is never overwritten
        self.assertIsNone(runner.create("kept_safe", '"""Second version."""\nprint("y")\n'))

    def test_remove_deletes_the_script(self):
        self._track("temporary_tool")
        runner.create("temporary_tool", '"""Temporary."""\nprint("x")\n')
        self.assertTrue(runner.remove("temporary_tool"))
        self.assertIsNone(runner.get("temporary_tool"))
        self.assertFalse(runner.remove("temporary_tool"))
        self.assertFalse(runner.remove("../escape"))


class ExecutionTests(ToolTestCase):
    """Running a script safely (spec sections 24, 28)."""

    def _echo(self):
        self._track("echo_tool")
        runner.create("echo_tool",
                      '"""Echo arguments.\n\nArguments: value\n"""\n'
                      "import sys\nprint('echo', *sys.argv[1:])\n")

    def test_run_returns_a_structured_result(self):
        self._echo()
        result = runner.run("echo_tool", ["a", "b"])
        self.assertEqual(set(result),
                         {"success", "exit_code", "stdout", "stderr", "duration"})
        self.assertTrue(result["success"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("echo a b", result["stdout"])
        self.assertIsInstance(result["duration"], float)

    def test_run_without_arguments_is_valid(self):
        self._track("argc_tool")
        runner.create("argc_tool", '"""Argc."""\nimport sys\nprint("argc:", len(sys.argv) - 1)\n')
        result = runner.run("argc_tool")
        self.assertTrue(result["success"])
        self.assertIn("argc: 0", result["stdout"])

    def test_unknown_tool_and_invalid_name(self):
        self.assertFalse(runner.run("no_such_tool")["success"])
        self.assertIn("not found", runner.run("no_such_tool")["stderr"].lower())
        self.assertFalse(runner.run("")["success"])
        self.assertFalse(runner.run(123)["success"])
        self.assertFalse(runner.run("../config")["success"])

    def test_invalid_arguments(self):
        self._echo()
        for bad in ("single-string", ["ok", {"bad": 1}], 42):
            result = runner.run("echo_tool", bad)
            self.assertFalse(result["success"])
            self.assertIn("invalid arguments", result["stderr"].lower())

    def test_invalid_timeout(self):
        self._echo()
        for bad in (-1, 0):
            result = runner.run("echo_tool", timeout=bad)
            self.assertFalse(result["success"])
            self.assertIn("invalid timeout", result["stderr"].lower())

    def test_timeout_is_applied(self):
        self._track("slow_tool")
        runner.create("slow_tool", '"""Slow."""\nimport time\ntime.sleep(5)\n')
        result = runner.run("slow_tool", timeout=1)
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["stderr"].lower())

    def test_failures_are_captured_not_raised(self):
        self._track("failing_tool")
        runner.create("failing_tool",
                      '"""Fail."""\nimport sys\nprint("boom", file=sys.stderr)\nsys.exit(3)\n')
        result = runner.run("failing_tool")
        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("boom", result["stderr"])

    def test_output_is_truncated(self):
        self._track("verbose_tool")
        runner.create("verbose_tool", '"""Verbose."""\nprint("x" * 1_100_000)\n')
        result = runner.run("verbose_tool")
        self.assertTrue(result["success"])
        self.assertTrue(result["stdout"].endswith("[output truncated]"))
        self.assertLess(len(result["stdout"]), 1_100_000)

    def test_only_scripts_in_the_tools_directory_run(self):
        # A symlink pointing outside the tools directory must be refused.
        link = config.TOOLS_SCRIPTS_DIR / "escape_link.py"
        try:
            link.symlink_to(config.BASE_DIR / "config.py")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not supported here")
        self.addCleanup(link.unlink, missing_ok=True)
        self.assertIsNotNone(runner.get("escape_link"))
        result = runner.run("escape_link")
        self.assertFalse(result["success"])
        self.assertIn("not permitted", result["stderr"].lower())


if __name__ == "__main__":
    unittest.main()