"""验证 CI 卷布局的系统身份检查。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


DEVICE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_layout", DEVICE / "scripts/check-ci-volume-layout.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VolumeLayoutTests(unittest.TestCase):
    def test_correct_layout_and_wrong_system_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            profile = directory / "profile.toml"
            profile.write_text('[root]\nos_volume_uuid="00000000-0000-0000-0000-000000000001"\n'
                               'systemos_volume_uuid="00000000-0000-0000-0000-000000000002"\n')
            layout = directory / "layout.json"
            values = {role: {"uuid": f"00000000-0000-0000-0000-{index:012d}"}
                      for role, index in (("os", 1), ("systemos", 2), ("data", 3))}
            layout.write_text(json.dumps(values))
            module.check(layout, profile)
            values["systemos"]["uuid"] = values["data"]["uuid"]
            layout.write_text(json.dumps(values))
            with self.assertRaisesRegex(ValueError, "systemos"):
                module.check(layout, profile)


if __name__ == "__main__":
    unittest.main()
