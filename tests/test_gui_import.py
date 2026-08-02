import importlib
import io
from contextlib import redirect_stdout
import unittest
from unittest import mock


class GuiImportTests(unittest.TestCase):
    def test_gui_imports_without_starting_application(self):
        module = importlib.import_module("wdpassport.gui")
        self.assertTrue(callable(module.main))

    def test_gui_help_does_not_require_gtk_imports(self):
        module = importlib.import_module("wdpassport.gui")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(module.main(["--help"]), 0)
        self.assertIn("Usage: wdpassport-gui", out.getvalue())

    def test_command_runner_has_a_timeout(self):
        module = importlib.import_module("wdpassport.gui")
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
            self.assertEqual(module.run_cmd(["example"]), (0, "", ""))
        self.assertEqual(run.call_args.kwargs["timeout"], module.COMMAND_TIMEOUT_SECONDS)

    def test_command_runner_reports_timeout(self):
        module = importlib.import_module("wdpassport.gui")
        failure = module.subprocess.TimeoutExpired("example", 1)
        with mock.patch.object(module.subprocess, "run", side_effect=failure):
            rc, _, err = module.run_cmd(["example"])
        self.assertEqual(rc, 124)
        self.assertIn("timed out", err)


if __name__ == "__main__":
    unittest.main()
