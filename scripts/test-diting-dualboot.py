"""Menu transformation regressions; no phone or private system inputs."""
import importlib.util
from pathlib import Path
import tomllib
import unittest

spec = importlib.util.spec_from_file_location('dualboot', Path(__file__).with_name('prepare-diting-dualboot.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SOURCE = '''version = 1
[boot]
timeout = 3
default = "xnu"
[kits]
autoload = false
[[entry]]
id = "xnu"
title = "Diting iPadOS"
type = "xnu"
path = "Payloads/kernel.macho"
args = "cpus=8 diting_build=ipados18-22H374 diting_touch=1"
[[entry]]
id = "reset"
title = "Restart"
type = "action"
action = "reset"
'''


class MenuTests(unittest.TestCase):
    def test_preserves_boot_payload(self):
        old = tomllib.loads(SOURCE)
        new = tomllib.loads(module.make_menu(SOURCE))
        self.assertEqual(new['entry'][1], old['entry'][0])
        self.assertEqual(new['kits'], old['kits'])
        self.assertEqual([e['id'] for e in new['entry']], ['android', 'xnu', 'tools'])
        self.assertEqual(new['entry'][0]['action'], 'reset')
        self.assertEqual(new['boot']['default'], 'android')
        self.assertEqual(new['boot']['timeout'], 10)

    def test_repeat_generation(self):
        once = module.make_menu(SOURCE)
        self.assertEqual(module.make_menu(once), once)

    def test_rejects_wrong_device_and_ambiguous_payload(self):
        for text in (SOURCE.replace('diting_build=', 'wrong_build='),
                     SOURCE + '\n[[entry]]\ntype="xnu"\nid="other"\n',
                     SOURCE.replace('version = 1', 'version = 2')):
            with self.assertRaises(ValueError):
                module.make_menu(text)

    def test_timeout_bounds(self):
        for timeout in (0, -1, 61):
            with self.assertRaises(ValueError):
                module.make_menu(SOURCE, timeout)


if __name__ == '__main__':
    unittest.main()
