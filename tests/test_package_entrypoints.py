import importlib
import unittest


class PackageEntrypointTests(unittest.TestCase):
    def test_package_imports(self):
        module = importlib.import_module("wdpassport")
        self.assertIsInstance(module.__version__, str)

    def test_cli_module_imports_without_device_access(self):
        module = importlib.import_module("wdpassport.cli")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
