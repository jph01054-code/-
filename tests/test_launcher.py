from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from smartstore import launcher


class LauncherTests(unittest.TestCase):
    def test_startup_failure_is_logged_and_shown(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'startup-error.log'
            with patch.object(launcher, 'start_application', side_effect=RuntimeError('GUI startup failed')), \
                 patch.object(launcher, 'log_path', return_value=path), \
                 patch.object(launcher, 'show_error') as show, \
                 patch.object(launcher.traceback, 'print_exc'):
                self.assertEqual(launcher.main(), 1)
                self.assertIn('GUI startup failed', path.read_text(encoding='utf-8'))
                show.assert_called_once_with(path)

    def test_success_does_not_show_error(self):
        with patch.object(launcher, 'start_application') as start, \
             patch.object(launcher, 'show_error') as show:
            self.assertEqual(launcher.main(check=True), 0)
            start.assert_called_once_with(check=True)
            show.assert_not_called()

    def test_unwritable_log_still_shows_failure(self):
        with TemporaryDirectory() as directory:
            with patch.object(launcher, 'start_application', side_effect=RuntimeError('failed')), \
                 patch.object(launcher, 'log_path', return_value=Path(directory)), \
                 patch.object(launcher, 'show_error') as show, \
                 patch.object(launcher.traceback, 'print_exc'):
                self.assertEqual(launcher.main(), 1)
                show.assert_called_once_with(None)
