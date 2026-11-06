#!/usr/bin/env python3
"""检查静态 UEFI 系统内存与设备树保留区是否重叠。"""
import argparse
from pathlib import Path
import re
import subprocess


def reserved_regions(dtb):
    for prop in ("#address-cells", "#size-cells"):
        value = subprocess.check_output(
            ["fdtget", "-t", "x", str(dtb), "/reserved-memory", prop], text=True,
        ).strip()
        if value != "2":
            raise ValueError(f"/reserved-memory 的 {prop} 不是 2")
    nodes = subprocess.check_output(
        ["fdtget", "-l", str(dtb), "/reserved-memory"], text=True,
    ).splitlines()
    regions = []
    for name in nodes:
        node = "/reserved-memory/" + name
        raw = subprocess.run(["fdtget", "-t", "x", str(dtb), node, "reg"],
                             capture_output=True, text=True)
        if raw.returncode:
            raise ValueError(f"{node} 没有固定 reg，无法完成静态比较")
        cells = [int(cell, 16) for cell in raw.stdout.split()]
        if len(cells) % 4:
            raise ValueError(f"{node} 不是双地址、双长度 cell")
        for index in range(0, len(cells), 4):
            a, b, c, d = cells[index:index + 4]
            start, size = (a << 32) | b, (c << 32) | d
            regions.append((name, start, start + size))
    return regions


def firmware_regions(path):
    pattern = re.compile(
        r'\{\s*"([^"]+)"\s*,\s*(0x[\da-f]+)\s*,\s*(0x[\da-f]+)\s*,'
        r'\s*AddMem\s*,\s*SYS_MEM\s*,\s*SYS_MEM_CAP\s*,\s*(\w+)', re.I,
    )
    return [(name, int(start, 16), int(start, 16) + int(size, 16))
            for name, start, size, kind in pattern.findall(path.read_text())
            if kind.lower() != "reserv"]


def iomem_reserved(path):
    """保留 /proc/iomem 中标记为 reserved 的实际范围。"""
    pattern = re.compile(r'^\s*([0-9a-f]+)-([0-9a-f]+)\s*:\s*reserved\s*$', re.I)
    regions = []
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            start, inclusive_end = (int(value, 16) for value in match.groups())
            regions.append(("Android reserved", start, inclusive_end + 1))
    if not regions:
        raise ValueError("运行时内存图没有可识别的 reserved 范围")
    return regions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", type=Path)
    parser.add_argument("memory_map", type=Path)
    parser.add_argument("--iomem", type=Path, help="可选的本机只读 /proc/iomem 快照")
    args = parser.parse_args()
    reserved, firmware = reserved_regions(args.dtb), firmware_regions(args.memory_map)
    if args.iomem:
        reserved += iomem_reserved(args.iomem)
    if not reserved or not firmware:
        raise SystemExit("没有识别到保留区或固件系统内存，无法比较")
    conflicts = []
    for name, start, end in firmware:
        for other, low, high in reserved:
            if start < high and low < end:
                conflicts.append((name, other, max(start, low), min(end, high)))
    for name, other, low, high in conflicts:
        print(f"冲突：{name} / {other}，{low:#x}–{high:#x}")
    if conflicts:
        raise SystemExit(f"发现 {len(conflicts)} 处冲突")
    print(f"静态比较未发现重叠：{len(firmware)} 个固件区域、{len(reserved)} 个设备树保留区")
    print("仍需核实运行时内存、固件条件编译和设备所有权。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"无法完成内存图比较：{error}") from error
