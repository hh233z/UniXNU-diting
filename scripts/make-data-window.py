#!/usr/bin/env python3
"""Build the Data window: a GPT disk with one APFS partition, ready for the SHNGROOT manifest.

The storage driver accepts the Data window only when it looks like a disk rather than a bare
container: it checks for `EFI PART` at offset 512. The reference board ships an 8 GiB APFS Data
image produced by `hdiutil create -fs APFS`, which is exactly a GPT with one Apple APFS partition.
This reproduces that on Linux with sgdisk and mkapfs.

The volume UUID matters: the kernel compares the Data volume against the UUID the build compiles in
(`XNU_OWNER_DATA_VOLUME_UUID`). Pass it with --uuid; mkapfs takes the volume UUID as -u (its -U
sets the container UUID instead).

Usage:
    make-data-window.py <output.img> [--gib 8] [--label Data] [--uuid UUID]

Requires sgdisk (gdisk) and mkapfs (apfsprogs).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

APFS_PARTITION_GUID = '7C3457EF-0000-11AA-AA11-00306543ECAC'


def tool(name):
    path = shutil.which(name)
    if not path:
        raise SystemExit(f'{name} not found: install gdisk, or apfsprogs for mkapfs')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--gib', type=int, default=8)
    parser.add_argument('--label', default='Data')
    parser.add_argument('--uuid', help='APFS volume UUID the kernel expects')
    args = parser.parse_args()
    sgdisk = tool('sgdisk')
    mkapfs = tool('mkapfs')
    total = args.gib << 30
    with args.output.open('wb') as handle:
        handle.truncate(total)
    subprocess.run([sgdisk, '--clear', '--set-alignment=2048', '--new', '1:0:0',
                    '--typecode', f'1:{APFS_PARTITION_GUID}', '--change-name', f'1:{args.label}',
                    str(args.output)], check=True, capture_output=True)
    info = subprocess.run([sgdisk, '--info=1', str(args.output)], check=True,
                          capture_output=True, text=True).stdout
    first = last = None
    for line in info.splitlines():
        if line.startswith('First sector:'):
            first = int(line.split(':', 1)[1].split()[0])
        elif line.startswith('Last sector:'):
            last = int(line.split(':', 1)[1].split()[0])
    if first is None or last is None:
        raise SystemExit(f'could not read the partition extent from sgdisk:\n{info}')
    blocks = (last - first + 1) // 8  # 512-byte sectors to 4 KiB blocks
    part = args.output.with_suffix('.apfs.img')
    with part.open('wb') as handle:
        handle.truncate(blocks * 4096)
    command = [mkapfs, '-L', args.label]
    if args.uuid:
        command += ['-u', args.uuid]
    subprocess.run(command + [str(part), str(blocks)], check=True, capture_output=True)
    with part.open('rb') as source, args.output.open('r+b') as target:
        target.seek(first * 512)
        shutil.copyfileobj(source, target, 8 << 20)
    part.unlink()
    with args.output.open('rb') as handle:
        handle.seek(512)
        signature = handle.read(8)
        handle.seek(first * 512 + 32)
        magic = handle.read(4)
    print(f'{args.output}: {total} bytes, partition at sector {first} ({blocks} 4 KiB blocks), '
          f'GPT {signature!r}, APFS {magic!r}', file=sys.stderr)
    if signature != b'EFI PART' or magic != b'NXSB':
        raise SystemExit('the assembled window is not a GPT disk with an APFS partition')


if __name__ == '__main__':
    main()