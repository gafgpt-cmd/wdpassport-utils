import importlib
import io
from contextlib import redirect_stdout
import unittest


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


if __name__ == "__main__":
    unittest.main()
