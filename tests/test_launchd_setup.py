import unittest
from pathlib import Path
import launchd_setup as setup

class SetupTests(unittest.TestCase):
    def test_service_plists(self):
        for service in ('alarm', 'dashboard', 'iphone'):
            value = setup.configuration(service)
            self.assertTrue(Path(value['ProgramArguments'][0]).is_absolute())
            self.assertEqual(value['ThrottleInterval'], 60)
            self.assertTrue(value['KeepAlive'])
            self.assertIn('Application Support', value['StandardOutPath'])
        self.assertIn('run', setup.configuration('alarm')['ProgramArguments'])
    def test_invalid_service(self):
        with self.assertRaises(ValueError): setup.configuration('other')

class PreflightTests(unittest.TestCase):
    def test_failed_preflight_does_not_mutate(self):
        from unittest.mock import patch
        with patch('launchd_setup.platform.system', return_value='Linux'), patch('launchd_setup.manage') as manage, patch('builtins.print'):
            self.assertEqual(setup.main(['install']), 1)
            manage.assert_not_called()
    def test_private_iphone_configuration(self):
        value = setup.configuration('iphone')
        self.assertIn('--quiet', value['ProgramArguments'])
        self.assertEqual(value['Umask'], 0o077)
    def test_install_failure_is_friendly(self):
        from unittest.mock import patch
        import subprocess
        with patch('launchd_setup.preflight', return_value=[]), patch('launchd_setup.manage', side_effect=subprocess.CalledProcessError(1, 'bootstrap')), patch('builtins.print'):
            self.assertEqual(setup.main(['install', '--services', 'dashboard']), 1)

class LogPermissionTests(unittest.TestCase):
    def test_preserves_contents_and_unselected_logs(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory) / 'logs'
            logs.mkdir()
            selected = logs / 'alarm.log'
            other = logs / 'iphone.log'
            selected.write_text('keep')
            other.write_text('other')
            selected.chmod(0o644)
            other.chmod(0o644)
            with patch('launchd_setup.LOGS', logs):
                setup.secure_logs('alarm')
            self.assertEqual(logs.stat().st_mode & 0o777, 0o700)
            self.assertEqual(selected.stat().st_mode & 0o777, 0o600)
            self.assertEqual(other.stat().st_mode & 0o777, 0o644)
            self.assertEqual(selected.read_text(), 'keep')
