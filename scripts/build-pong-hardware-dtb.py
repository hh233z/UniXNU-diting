#!/usr/bin/env python3
"""Build the boot image's device tree from the board DTS, inside the build tree.

A firmware preflight script: unixnu runs it with the build tree as the working
directory and UNIXNU_UEFI / UNIXNU_DEVICE in the environment, and the boot image
names its output in board.toml [bootimg] dtb. The device tree is the one the
firmware hands to the kernel, so it is compiled once, here, and never copied
from a workstation.

The board DTS, its include directories and the output path are read from
board.toml ([device_tree] source and include_dirs, [bootimg] dtb) unless a flag
overrides them, so the device tree the firmware carries is the one the board
declares. Before this, the default was dts/pong.dts for every board.
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
    record = {'source': str(source), 'includes': [str(item) for item in directories],
              'output': str(output), 'bytes': len(data)}
    output.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
