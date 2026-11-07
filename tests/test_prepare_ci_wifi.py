"""用本地 Git 仓库验证 CI Wi-Fi 稀疏检出和版本固定。"""
import os
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare-ci-wifi.py"
spec = importlib.util.spec_from_file_location("prepare_wifi", SCRIPT)
prepare_wifi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_wifi)


def git(root, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
    return subprocess.check_output(["git", "-C", str(root), *args], env=env, text=True).strip()


def make_repo(root, files):
    root.mkdir()
    git(root, "init", "--quiet")
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "fixture")
    return git(root, "rev-parse", "HEAD")


class PrepareWifiTests(unittest.TestCase):
    def test_sparse_checkout_includes_mhi_qmi_and_pinned_submodule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linux = root / "linux-source"
            linux_files = ["drivers/net/wireless/ath/ath11k/pci.c", "drivers/bus/mhi/common.h",
                           "include/net/mac80211.h", "drivers/soc/qcom/qmi_interface.c",
                           "drivers/soc/qcom/qmi_encdec.c", "drivers/net/wireless/ath/spectral_common.h",
                           "drivers/net/wireless/ath/ath11k/core.h"]
            linux_files += [f"drivers/bus/mhi/host/{name}" for name in ("init.c", "main.c", "pm.c", "boot.c", "internal.h")]
            linux_files += [f"drivers/net/wireless/ath/ath11k/{name}.c" for name in prepare_wifi.ATH11K_SOURCES]
            linux_files += [f"include/{name}" for name in prepare_wifi.LINUX_HEADERS]
            linux_sha = make_repo(linux, linux_files)
            shared = root / "wifi-source"
            shared_files = ["include/nw_abi.h", "shim/libc/stdint.h", *prepare_wifi.SHARED_SOURCES]
            shared_sha = make_repo(shared, shared_files)
            sheng = root / "sheng-source"
            make_repo(sheng, ["package/QcomRpmh.c", "package/QcomRpmh.h"])
            (sheng / ".gitmodules").write_text('[submodule "drivers/Ath12kWifi"]\n'
                                               '\tpath = drivers/Ath12kWifi\n'
                                               f'\turl = {shared.as_uri()}\n')
            git(sheng, "add", ".gitmodules")
            git(sheng, "update-index", "--add", "--cacheinfo", f"160000,{shared_sha},drivers/Ath12kWifi")
            git(sheng, "commit", "--quiet", "-m", "add wifi gitlink")
            sheng_sha = git(sheng, "rev-parse", "HEAD")
            manifest = root / "sources.toml"
            manifest.write_text(
                f'[[source]]\ninput="wifi_linux"\ngit="{linux.as_uri()}"\ncommit="{linux_sha}"\n'
                'required=["drivers/net/wireless/ath/ath11k/pci.c"]\n'
                f'[[source]]\ninput="sheng_source"\ngit="{sheng.as_uri()}"\ncommit="{sheng_sha}"\n'
                'required=["package/QcomRpmh.c", "package/QcomRpmh.h"]\n'
                f'[[source]]\ninput="wifi_shared"\ngit="{shared.as_uri()}"\ncommit="{shared_sha}"\n'
                'required=["include/nw_abi.h", "shim/src/lx_rt.c", "src/nw_sta.c"]\n'
            )
            workspace = root / "workspace"
            workspace.mkdir()
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace),
                            "--manifest", str(manifest), "--shared-url", shared.as_uri()],
                           check=True, capture_output=True, text=True)
            self.assertEqual(git(workspace / "sheng/drivers/Ath12kWifi", "rev-parse", "HEAD"), shared_sha)
            self.assertTrue((workspace / "linux/drivers/bus/mhi/host/boot.c").is_file())
            self.assertTrue((workspace / "linux/drivers/soc/qcom/qmi_encdec.c").is_file())
            result = subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace),
                                     "--manifest", str(manifest)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("拒绝覆盖", result.stderr)
            mismatch = root / "mismatch.toml"
            mismatch.write_text(manifest.read_text().replace(shared_sha, "0" * 40))
            other_workspace = root / "mismatch-workspace"
            other_workspace.mkdir()
            result = subprocess.run(["python3", str(SCRIPT), "--workspace", str(other_workspace),
                                     "--manifest", str(mismatch)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("子模块与清单不一致", result.stderr)


if __name__ == "__main__":
    unittest.main()
