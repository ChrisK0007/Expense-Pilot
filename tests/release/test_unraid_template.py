from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class UnraidTemplateTests(unittest.TestCase):
    def test_public_template_and_profile_match_real_repository_files(self):
        template = ET.parse(ROOT / 'deploy/unraid/expense-pilot.xml').getroot()
        profile = ET.parse(ROOT / 'ca_profile.xml').getroot()
        self.assertTrue(profile.findtext('Profile').strip())
        prefix = 'https://raw.githubusercontent.com/ChrisK0007/Expense-Pilot/'
        for node, field in [(template, 'Icon'), (template, 'TemplateURL'), (template, 'ReadMe'), (profile, 'Icon')]:
            url = node.findtext(field)
            self.assertTrue(url.startswith(prefix), url)
            channel, path = url.removeprefix(prefix).split('/', 1)
            self.assertIn(channel, ('main', 'beta'))
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertEqual(template.findtext('Privileged'), 'false')
        self.assertNotIn('docker.sock', ET.tostring(template).decode())
        config = {c.attrib['Target']: c for c in template.findall('Config')}
        self.assertEqual(config['SETUP_TOKEN'].attrib['Required'], 'false')
        self.assertFalse(any(name.startswith('OLLAMA') for name in config))
        self.assertEqual(config['/data'].attrib['Mode'], 'rw')
