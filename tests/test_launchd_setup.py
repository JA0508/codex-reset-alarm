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
