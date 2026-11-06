"""验证 Diting 保留区与固件映射的冲突检查。"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


DEVICE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_memory", DEVICE / "scripts/check-firmware-memory.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FirmwareMemoryTests(unittest.TestCase):
    def test_pong_fd_overlaps_diting_ramoops(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            subprocess.run(
                ["python3", str(DEVICE / "scripts/build-pong-hardware-dtb.py")],
                cwd=work, env={**os.environ, "UNIXNU_DEVICE": str(DEVICE)},
                check=True, capture_output=True, text=True,
            )
            reserved = module.reserved_regions(work / "build/pong/pong.dtb")
            memory_map = work / "MemoryMapLib.c"
            memory_map.write_text(
                '{"UEFI FD", 0xA7100000, 0x00300000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK},\n'
                '{"Safe example", 0xA7400000, 0x00300000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK},\n'
            )
            regions = module.firmware_regions(memory_map)
            overlaps = {name: [other for other, low, high in reserved if start < high and low < end]
                        for name, start, end in regions}
            self.assertIn("ramoops@a7000000", overlaps["UEFI FD"])
            self.assertEqual(overlaps["Safe example"], [])


if __name__ == "__main__":
    unittest.main()
