#!/usr/bin/env python3
"""为 CI 准备与设备配置固定版本一致的 Wi-Fi 源码。"""
import argparse
import os
from pathlib import Path
import subprocess
import tomllib


ATH11K_SOURCES = "core hal hal_tx hal_rx wmi mac reg htc qmi dp dp_tx dp_rx ce peer dbring hw pcic fw p2p mhi pci".split()
MHI_SOURCES = ("init.c", "main.c", "pm.c", "boot.c", "internal.h")
SHARED_SOURCES = ("src/nw_crypto.c", "src/nw_mac80211.c", "src/nw_net.c", "src/nw_pci.c",
                  "src/nw_qrtr.c", "src/nw_qrtr_mhi.c", "src/nw_sta.c", "shim/src/lx_rt.c",
                  "shim/src/mhi_hook.c", "shim/mhi/trace.h", "shim/include/lx.h")
LINUX_HEADERS = ("linux/mhi.h", "linux/ieee80211.h", "linux/soc/qcom/qmi.h", "net/cfg80211.h",
                 "net/regulatory.h", "net/codel.h", "net/ieee80211_radiotap.h",
                 "uapi/linux/nl80211.h", "uapi/linux/rfkill.h", "net/mac80211.h")


def git(directory, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(directory), *arguments], text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).strip()


def checkout(path, url, commit, patterns, cone):
    if path.exists():
        raise SystemExit(f"目标已存在，拒绝覆盖：{path}")
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    git(path, "remote", "add", "origin", url)
    git(path, "-c", "protocol.file.allow=always", "fetch", "--quiet", "--depth=1",
        "--filter=blob:none", "origin", commit)
    git(path, "sparse-checkout", "init", "--cone" if cone else "--no-cone")
    git(path, "sparse-checkout", "set", *patterns)
    git(path, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    if git(path, "rev-parse", "HEAD") != commit:
        raise SystemExit(f"源码版本不匹配：{path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--linux-url")
    parser.add_argument("--sheng-url")
    parser.add_argument("--shared-url")
    args = parser.parse_args()
    sources = {item["input"]: item for item in tomllib.loads(args.manifest.read_text())["source"]}
    linux_spec, sheng_spec, shared_spec = (sources[key] for key in ("wifi_linux", "sheng_source", "wifi_shared"))
    workspace = args.workspace.resolve()
    linux, sheng = workspace / "linux", workspace / "sheng"
    if linux.exists() or sheng.exists():
        raise SystemExit("linux 或 sheng 目标已存在，拒绝覆盖")

    checkout(linux, args.linux_url or linux_spec["git"], linux_spec["commit"],
             ["drivers/net/wireless/ath", "drivers/bus/mhi", "drivers/soc/qcom", "include"], True)
    checkout(sheng, args.sheng_url or sheng_spec["git"], sheng_spec["commit"],
             ["/.gitmodules", "/package/", "/drivers/Ath12kWifi"], False)
    gitlink = git(sheng, "ls-tree", "HEAD", "drivers/Ath12kWifi").split()
    if len(gitlink) < 3 or gitlink[2] != shared_spec["commit"]:
        raise SystemExit("Sheng 固定版本的 Wi-Fi 子模块与清单不一致")
    command = ["-c", "protocol.file.allow=always"]
    if args.shared_url:
        command += ["-c", f"submodule.drivers/Ath12kWifi.url={args.shared_url}"]
    git(sheng, *command, "submodule", "update", "--init", "--depth=1", "--", "drivers/Ath12kWifi")
    shared = sheng / "drivers/Ath12kWifi"
    if git(shared, "rev-parse", "HEAD") != shared_spec["commit"]:
        raise SystemExit("Wi-Fi 子模块的实际版本与清单不一致")

    linux_files = [*linux_spec["required"], "drivers/net/wireless/ath/spectral_common.h",
                   *[f"drivers/net/wireless/ath/ath11k/{name}.c" for name in ATH11K_SOURCES],
                   "drivers/net/wireless/ath/ath11k/core.h", "drivers/bus/mhi/common.h",
                   *[f"drivers/bus/mhi/host/{name}" for name in MHI_SOURCES],
                   *[f"drivers/soc/qcom/{name}" for name in ("qmi_interface.c", "qmi_encdec.c")],
                   *[f"include/{name}" for name in LINUX_HEADERS]]
    shared_files = [*shared_spec["required"], *SHARED_SOURCES]
    missing = [str(linux / path) for path in linux_files if not (linux / path).is_file()]
    missing += [str(shared / path) for path in shared_files if not (shared / path).is_file()]
    missing += [str(sheng / path) for path in sheng_spec["required"] if not (sheng / path).is_file()]
    if missing:
        raise SystemExit("Wi-Fi 构建输入缺失：\n" + "\n".join(missing))
    if not (shared / "shim/libc").is_dir() or not (shared / "shim/include").is_dir():
        raise SystemExit("Wi-Fi 构建需要完整的 shim 头文件目录")
    print(f"Linux: {linux_spec['commit']}\nSheng: {sheng_spec['commit']}\nWi-Fi: {shared_spec['commit']}")


if __name__ == "__main__":
    main()
