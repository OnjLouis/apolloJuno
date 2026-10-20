import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.folder = self.root / 'apolloJuno'
        self.folder.mkdir()
        self.old = self.folder / 'apolloJuno.dic'
        self.new = self.folder / 'apolloJuno-Juno (calibrated).dic'
        self.names = Mock(return_value=self.new.name)
        modules = {
            'NVDAState': types.SimpleNamespace(WritePaths=types.SimpleNamespace(voiceDictsDir=str(self.root))),
            'speechDictHandler': types.SimpleNamespace(dictFormatUpgrade=types.SimpleNamespace(
                createVoiceDictFileName=self.names)),
        }
        with patch.dict(sys.modules, modules):
            path = Path(__file__).resolve().parents[1] / 'addon/installTasks.py'
            spec = importlib.util.spec_from_file_location('apollo_install_test', path)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def test_existing_dictionary_is_copied_without_changing_the_original(self):
        content = b'# user entry\nexample\treplacement\t0\t1\n'
        self.old.write_bytes(content)
        self.module.onInstall()
        self.assertEqual(self.old.read_bytes(), content)
        self.assertEqual(self.new.read_bytes(), content)
        self.names.assert_called_once_with('apolloJuno', 'Juno (calibrated)')
        self.assertEqual(len(list(self.folder.iterdir())), 2)

    def test_newer_dictionary_is_not_overwritten(self):
        self.old.write_bytes(b'old')
        self.new.write_bytes(b'new')
        self.module.onInstall()
        self.assertEqual(self.new.read_bytes(), b'new')
        self.assertEqual(self.old.read_bytes(), b'old')

    def test_fresh_install_does_not_create_dictionary_files(self):
        self.module.onInstall()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_repeated_install_is_idempotent(self):
        self.old.write_bytes(b'old')
        self.module.onInstall()
        self.new.write_bytes(b'edited')
        self.module.onInstall()
        self.assertEqual(self.new.read_bytes(), b'edited')

    def test_failed_copy_preserves_source_and_removes_incomplete_destination(self):
        self.old.write_bytes(b'old')
        with patch.object(self.module.shutil, 'copyfileobj', side_effect=OSError('test write failure')):
            with self.assertRaises(OSError):
                self.module.onInstall()
        self.assertEqual(self.old.read_bytes(), b'old')
        self.assertFalse(self.new.exists())


if __name__ == '__main__':
    unittest.main()
