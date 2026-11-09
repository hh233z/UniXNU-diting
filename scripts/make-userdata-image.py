#!/usr/bin/env python3
"""Assemble the userdata image: a SHNGROOT manifest followed by whole disk windows.

Layout written here (little endian, matching drivers/NativeUfs/RootLayout.h):

    0x000000  manifest block, 4096 bytes: 'SHNGROOT', version 1, window count, image bytes,
              then 128-byte entries {name[32], offset, size, block 512, flags 1, sha256, 40 pad},
              zero padded to the first 1 MiB, with the SHA-256 of bytes 0..4063 at 4064.
    0x100000  window 'OS'        raw APFS container of the restore
    ....      window 'SystemOS'  raw SystemOS cryptex container
    ....      window 'Data'      GPT disk with one APFS partition (make-data-window.py)

The geometry comes from board.toml [userdata]; the image is rejected when it would not fit.

Usage:
    make-userdata-image.py --os OS.dmg --systemos SystemOS.dmg --data Data.img [--out dir]
"""
import argparse
import hashlib
import json
import struct
import sys
import tomllib
from pathlib import Path

MIB = 1 << 20
ROOT = Path(__file__).resolve().parents[1]


def digest(path, handle):
    result = hashlib.sha256()
    handle.seek(0)
    left = path.stat().st_size
    while left:
        chunk = handle.read(min(8 * MIB, left))
        if not chunk:
            raise SystemExit(f'{path}: short read')
        result.update(chunk)
        left -= len(chunk)
    return result.digest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--os', type=Path, required=True)
    parser.add_argument('--systemos', type=Path, required=True)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--board', type=Path, default=ROOT / 'board.toml')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/userdata')
    args = parser.parse_args()

    board = tomllib.loads(args.board.read_text())
    spec = board['userdata']
    block = spec.get('lba_bytes', 4096)
    capacity = (spec['last_lba'] - spec['first_lba'] + 1) * block
    windows = [('OS', args.os), ('SystemOS', args.systemos)]
    if args.data:
        windows.append(('Data', args.data))
    for name, path in windows:
        size = path.stat().st_size
        if not size or size % 4096 or (name == 'Data' and size % 512):
            raise SystemExit(f'{name}: {path} is not a whole 4 KiB block image')

    layout, cursor = [], MIB
    for name, path in windows:
        if name == 'Data':
            cursor = (cursor + 16 * MIB - 1) // (16 * MIB) * (16 * MIB)
        layout.append((name, cursor, path.stat().st_size))
        cursor = (cursor + path.stat().st_size + MIB - 1) // MIB * MIB
    total = cursor
    print(f'image {total} bytes ({total / 2**30:.2f} GiB) of a {capacity / 2**30:.2f} GiB partition',
          file=sys.stderr)
    if total > capacity:
        raise SystemExit('the windows do not fit in the userdata partition')

    args.out.mkdir(parents=True, exist_ok=True)
    image = args.out / 'userdata-root.img'
    entries = []
    with image.open('wb') as out:
        out.truncate(total)
        for (name, offset, size), (_, path) in zip(layout, windows):
            out.seek(offset)
            with path.open('rb') as source:
                while True:
                    chunk = source.read(8 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            with path.open('rb') as handle:
                entries.append((name, offset, size, digest(path, handle)))
            print(f'  {name}: {size} bytes at {offset:#x}', file=sys.stderr)
        header = bytearray(4096)
        header[0:8] = b'SHNGROOT'
        struct.pack_into('<IIQ', header, 8, 1, len(entries), total)
        for index, (name, offset, size, sha) in enumerate(entries):
            struct.pack_into('<32sQQII32s40s', header, 24 + 128 * index, name.encode(), offset,
                             size, 512, 1, sha, bytes(40))
        header[4064:4096] = hashlib.sha256(bytes(header[:4064])).digest()
        out.seek(0)
        out.write(header)
    report = {'image_bytes': total, 'first_lba': spec['first_lba'], 'last_lba': spec['last_lba'],
              'lba_bytes': block, 'userdata_bytes': capacity,
              'windows': [{'name': n, 'offset': o, 'size': s, 'sha256': d.hex()}
                          for n, o, s, d in entries]}
    (args.out / 'userdata-root.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'wrote {image} and userdata-root.json', file=sys.stderr)


if __name__ == '__main__':
    main()