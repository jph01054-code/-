import os
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch
from smartstore.tk_runtime import configure_tk_paths


class TkRuntimeTests(unittest.TestCase):
    def configure(self, root, environment):
        extension = types.SimpleNamespace(TCL_VERSION='8.6', TK_VERSION='8.6')
        with patch('smartstore.tk_runtime.sys.platform', 'win32'), \
             patch('smartstore.tk_runtime.sys.base_prefix', str(root)), \
             patch.dict('sys.modules', {'_tkinter': extension}), \
             patch('smartstore.tk_runtime.os.environ', environment):
            return configure_tk_paths()

    def libraries(self, root):
        tcl, tk = root/'tcl'/'tcl8.6', root/'tcl'/'tk8.6'
        tcl.mkdir(parents=True)
        tk.mkdir(parents=True)
        (tcl/'init.tcl').write_text('# test fixture')
        (tk/'tk.tcl').write_text('# test fixture')
        return tcl, tk

    def test_unicode_install_path_and_venv_base(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)/'사용자'/'Python313'
            tcl, tk = self.libraries(base)
            environment = {}
            self.assertTrue(self.configure(base, environment))
            self.assertEqual(environment['TCL_LIBRARY'], str(tcl))
            self.assertEqual(environment['TK_LIBRARY'], str(tk))

    def test_missing_files_not_invented(self):
        with TemporaryDirectory() as directory:
            environment = {}
            self.assertFalse(self.configure(Path(directory), environment))
            self.assertEqual(environment, {})

    def test_incomplete_pair_not_activated(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            _, tk = self.libraries(base)
            (tk/'tk.tcl').unlink()
            environment = {}
            self.assertFalse(self.configure(base, environment))
            self.assertEqual(environment, {})

    def test_existing_overrides_preserved(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            self.libraries(base)
            environment = {'TCL_LIBRARY':'custom-tcl', 'TK_LIBRARY':'custom-tk'}
            self.assertTrue(self.configure(base, environment))
            self.assertEqual(environment, {'TCL_LIBRARY':'custom-tcl', 'TK_LIBRARY':'custom-tk'})

    def test_idempotent(self):
        with TemporaryDirectory() as directory:
            base=Path(directory)
            self.libraries(base)
            environment={}
            self.configure(base,environment)
            before=dict(environment)
            self.configure(base,environment)
            self.assertEqual(environment,before)

    def test_non_windows_environment_unchanged(self):
        with patch('smartstore.tk_runtime.sys.platform','linux'), \
             patch('smartstore.tk_runtime.os.environ',{}) as environment:
            self.assertFalse(configure_tk_paths())
            self.assertEqual(environment,{})
