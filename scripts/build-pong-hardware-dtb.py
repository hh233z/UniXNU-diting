#!/usr/bin/env python3
"""根据板级配置编译启动镜像使用的设备树。

固件预处理在构建树中运行，输出位置由 board.toml 的 [bootimg] dtb 指定。
UEFI 的 FDF 可能另行嵌入设备树；本脚本不会替换或验证那份固件输入。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def dtc():
    for name in ('dtc',):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('dtc is missing; install it (brew install dtc)')


def board_spec(device):
    path = device / 'board.toml'
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text())


def soc_root(device):
    """The SoC seed that a "soc:" prefix names: feeds.toml, kind = "soc", path."""
    feeds = device / 'feeds.toml'
    if feeds.is_file():
        for source in tomllib.loads(feeds.read_text()).get('source', []):
            if source.get('kind') == 'soc' and source.get('path'):
                return device / source['path']
    raise SystemExit(f'{feeds}: no kind = "soc" entry with a path; an include with the soc: prefix cannot resolve')


def resolve(device, tree, entry):
    """Resolve a "kind:path" entry the way board.toml names it."""
    kind, _, relative = entry.partition(':')
    if not relative:
        kind, relative = 'device', entry
    if kind == 'device':
        return (device / relative).resolve()
    if kind == 'soc':
        return (soc_root(device) / relative).resolve()
    return (tree / relative).resolve()


def publish_drivers(device, tree):
    """Expose the device drivers in the tree EDK II reads.

    board.toml [firmware] packages names {tree}/drivers/<module>, and the tree only carries
    the modules the component catalog resolves. A board driver that ships in this repository
    (drivers/<name>) is not one of them, so EDK II stopped with 'One Path in PACKAGES_PATH
    doesn't exist'. Link every device driver in before the build; the assembled tree owns
    drivers/ and re-clears it on the next assemble, so this runs on every firmware build.
    """
    source = device / 'drivers'
    target = tree / 'drivers'
    if not source.is_dir():
        return []
    target.mkdir(parents=True, exist_ok=True)
    published = []
    for driver in sorted(source.iterdir()):
        if not driver.is_dir():
            continue
        link = target / driver.name
        if link.exists() or link.is_symlink():
            continue
        link.symlink_to(driver.resolve())
        published.append(driver.name)
    return published

def main():
    device = Path(os.environ.get('UNIXNU_DEVICE', Path(__file__).resolve().parents[1])).resolve()
    tree = Path.cwd()
    board = board_spec(device)
    spec = board.get('device_tree', {})
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=spec.get('source', 'device:dts/pong.dts'),
                        help='board DTS as board.toml names it (device:dts/<board>.dts)')
    parser.add_argument('--include', action='append', default=None,
                        help='include directory as board.toml names it (device:/soc:/tree:); repeatable')
    parser.add_argument('--output', default=board.get('bootimg', {}).get('dtb', 'build/pong/pong.dtb'),
                        help='output, relative to the build tree')
    args = parser.parse_args()
    source = resolve(device, tree, args.source)
    if not source.is_file():
        raise SystemExit(f'{source} missing: {args.source} is the board DTS of this repository')
    entries = args.include if args.include else spec.get('include_dirs', ['soc:dts'])
    directories = []
    for entry in entries:
        directory = resolve(device, tree, entry)
        if not directory.is_dir():
            raise SystemExit(f'{directory} missing: {entry} names an include directory')
        directories.append(directory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [dtc(), '-I', 'dts', '-O', 'dtb', '-o', str(output)]
    for directory in directories:
        command += ['-i', str(directory)]
    subprocess.run([*command, str(source)], check=True)
    data = output.read_bytes()
    if data[:4] != b'\xd0\x0d\xfe\xed':
        raise SystemExit(f'{output} is not a flattened device tree')
    firmware_tree = None
    if board.get('firmware', {}).get('config') == 'diting' and os.environ.get('UNIXNU_UEFI'):
        firmware_tree = (Path(os.environ['UNIXNU_UEFI']) /
                         'Platforms/Xiaomi/ditingPkg/FdtBlob/sm8475-xiaomi-diting.dtb')
        if not firmware_tree.parent.is_dir():
            raise SystemExit(f'{firmware_tree.parent} missing: not a Diting firmware checkout')
        firmware_tree.write_bytes(data)
    record = {'source': str(source), 'includes': [str(item) for item in directories],
              'output': str(output), 'bytes': len(data),
              'firmware_dtb': str(firmware_tree) if firmware_tree else None}
    output.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')

    published = publish_drivers(device, tree)
    if published:
        print(f'device drivers published to the build tree: {", ".join(published)}')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
