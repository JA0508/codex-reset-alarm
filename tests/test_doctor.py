import unittest
from unittest.mock import patch
import doctor

class DoctorTests(unittest.TestCase):
    def test_missing_platform_is_failure(self):
        with patch('doctor.platform.system', return_value='Linux'), patch('doctor.os.path.isfile', return_value=False), patch('doctor.port_open', return_value=False), patch('doctor.launchd_loaded', return_value=False):
            report = doctor.diagnose()
            self.assertFalse(report['ok'])
            self.assertFalse(report['checks']['macos']['ok'])
            self.assertNotIn('/Users/', str(report))
    def test_available_dependencies(self):
        with patch('doctor.platform.system', return_value='Darwin'), patch('doctor.os.path.isfile', return_value=True), patch('doctor.os.access', return_value=True), patch('doctor.port_open', return_value=True), patch('doctor.launchd_loaded', return_value=True):
            self.assertTrue(doctor.diagnose()['ok'])
