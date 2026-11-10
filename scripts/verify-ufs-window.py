#!/usr/bin/env python3
"""Compare one installed SHNGROOT UFS window with the image that was written.

The installers stream a whole window with dd and can be interrupted without a
visible error, so acceptance has to read the window back. This reads the 4 KiB
SHNGROOT directory, then samples 64 KiB at evenly spaced offsets across the
window and compares their SHA-256 with the same offsets in the local image. A
sequential dd that matches head, interior and tail proves the stream reached
the end without a short write; it is deliberately not a full-image readback.

Read-only: the only device command is dd from the userdata partition.

Usage:
    verify-ufs-window.py --serial 9e0c2b55 --window OS --image OS.img
    verify-ufs-window.py --serial 9e0c2b55 --window Data --image Data.img --samples 6
"""
import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

TARGET = '/dev/block/by-name/userdata'
CHUNK = 64 << 10


def run_adb(adb, serial, args):
    command = [adb, '-s', serial] + args
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise SystemExit('%s failed (%d): %s' % (' '.join(command), result.returncode,
                                                 result.stderr.decode('latin1', 'replace')))
    return result.stdout


def read_device(adb, serial, offset, length):
    if offset % 4096 or length % 4096:
        raise SystemExit('device reads must be 4 KiB aligned')
    return run_adb(adb, serial, ['exec-out', 'dd', 'if=' + TARGET, 'bs=4096',
                                 'skip=%d' % (offset // 4096), 'count=%d' % (length // 4096),
                                 'status=none'])


def parse_directory(raw):
    if len(raw) != 4096 or raw[:8] != b'SHNGROOT':
        raise SystemExit('no SHNGROOT directory at the start of userdata')
    version, count, total = struct.unpack_from('<IIQ', raw, 8)
    if version != 1 or not count or count > 4:
        raise SystemExit(f'unsupported directory version={version} count={count}')
    if hashlib.sha256(raw[:4064]).digest() != raw[4064:4096]:
        raise SystemExit('SHNGROOT directory checksum mismatch')
    windows = {}
    for i in range(count):
        name, offset, size, block, flags, sha, _pad = struct.unpack_from(
            '<32sQQII32s40s', raw, 24 + 128 * i)
        windows[name.split(b'\0')[0].decode('ascii')] = dict(
            offset=offset, size=size, block=block, flags=flags, sha256=sha.hex())
    return windows, total


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--window', required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--samples', type=int, default=6)
    parser.add_argument('--expect-uuid', help='accepted only for readability of the report')
    args = parser.parse_args()
    adb = shutil.which(args.adb) or args.adb
    if not 2 <= args.samples <= 32:
        raise SystemExit('--samples must be between 2 and 32')
    if not args.image.is_file():
        raise SystemExit('image not found: ' + str(args.image))
    directory = read_device(adb, args.serial, 0, 4096)
    windows, total = parse_directory(directory)
    print(f'SHNGROOT v1: {len(windows)} windows, image bytes {total}')
    if args.window not in windows:
        raise SystemExit(f'window {args.window} not in directory: {sorted(windows)}')
    window = windows[args.window]
    image_bytes = args.image.stat().st_size
    print(f'{args.window}: offset {window["offset"]:#x} bytes {window["size"]} '
          f'recorded sha256 {window["sha256"]} block {window["block"]}')
    if image_bytes != window["size"]:
        raise SystemExit(f'image is {image_bytes} bytes, window is {window["size"]} bytes')
    ok = True
    matches = 0
    with args.image.open('rb') as image:
        for index in range(args.samples):
            relative = (window["size"] - CHUNK) * index // (args.samples - 1)
            relative -= relative % 4096
            device = read_device(adb, args.serial, window["offset"] + relative, CHUNK)
            image.seek(relative)
            local = image.read(CHUNK)
            same = device == local
            matches += same
            print(f'  {relative / 2**30:8.3f} GiB  device {hashlib.sha256(device).hexdigest()[:16]}'
                  f'  image {hashlib.sha256(local).hexdigest()[:16]}  {"same" if same else "DIFF"}')
            if not same:
                ok = False
    print('note: the kernel only checks the directory checksum, not the per-window sha256; '
          'the sampled comparison above is the write evidence')
    print(('PASS' if ok else 'FAIL') + f': {matches}/{args.samples} sampled regions identical')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
