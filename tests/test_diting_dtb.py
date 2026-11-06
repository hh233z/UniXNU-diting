"""验证 Diting 设备树的地址编码。"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


DEVICE = Path(__file__).resolve().parents[1]


class DitingDtbTests(unittest.TestCase):
    def test_firmware_preflight_address_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            subprocess.run(
                ["python3", str(DEVICE / "scripts/build-pong-hardware-dtb.py")],
                cwd=work, env={**os.environ, "UNIXNU_DEVICE": str(DEVICE)},
                check=True, capture_output=True, text=True,
            )
            dtb = work / "build/pong/pong.dtb"
            expected = {
                ("/soc/spi@990000", "reg"): "0 990000 0 4000",
                ("/soc/qcom,mdss_mdp@ae00000", "reg"):
                    "0 ae00000 0 84000 0 aeb0000 0 2008 0 aeac000 0 800",
                ("/soc/ssusb@a600000", "reg"): "0 a600000 0 100000",
                ("/soc/ssusb@a600000", "ranges"): "a600000 0 a600000 100000",
                ("/gpio-controller@f000000", "#interrupt-cells"): "2",
                ("/gpio-controller@f000000", "interrupts"): "0 d0 4",
                ("/soc/ufs@1d84000", "reg"):
                    "0 1d84000 0 3000 0 1d88000 0 8000 0 1d90000 0 9000",
                ("/soc/ufs@1d84000", "interrupts"): "0 109 4",
            }
            for (node, prop), value in expected.items():
                with self.subTest(node=node, prop=prop):
                    actual = subprocess.check_output(
                        ["fdtget", "-t", "x", str(dtb), node, prop], text=True,
                    ).strip()
                    self.assertEqual(actual, value)

    def test_diting_firmware_receives_the_same_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device, work, firmware = root / "device", root / "work", root / "firmware"
            device.mkdir()
            work.mkdir()
            target = firmware / "Platforms/Xiaomi/ditingPkg/FdtBlob"
            target.mkdir(parents=True)
            board = (DEVICE / "board.toml").read_text()
            self.assertEqual(board.count('config = "pong"'), 1)
            (device / "board.toml").write_text(board.replace('config = "pong"', 'config = "diting"'))
            (device / "feeds.toml").symlink_to(DEVICE / "feeds.toml")
            (device / "dts").symlink_to(DEVICE / "dts", target_is_directory=True)
            (device / "migration").symlink_to(DEVICE / "migration", target_is_directory=True)
            subprocess.run(
                ["python3", str(DEVICE / "scripts/build-pong-hardware-dtb.py")],
                cwd=work, env={**os.environ, "UNIXNU_DEVICE": str(device), "UNIXNU_UEFI": str(firmware)},
                check=True, capture_output=True, text=True,
            )
            self.assertEqual((work / "build/pong/pong.dtb").read_bytes(),
                             (target / "sm8475-xiaomi-diting.dtb").read_bytes())


if __name__ == "__main__":
    unittest.main()
