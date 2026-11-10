#!/usr/bin/env python3
"""Inspect the APFS metadata of a UFS window, on the device or in a local image.

The UFS windows live inside the userdata partition and a boot is expensive and
one-way without a person at the phone. This reads only the APFS blocks the
container needs (superblock, checkpoint area, object map, volume superblock and
the extents of the files asked for), so volume UUIDs and key userland files can
be confirmed while the phone still sits in recovery. Read-only: no window is
written and no whole partition is read.

Both a bare APFS window (OS, SystemOS) and a GPT window with one APFS partition
(Data) are accepted. With --image the same report runs against a local window
source, so the two sides can be compared. A sealed volume (SystemOS) resolves its
live root through a snapshot that this reader does not walk, so file paths there
report "unreadable" while the container and volume checks still work.

Usage:
    read-ufs-window-apfs.py --serial 9e0c2b55 --window OS \
        --expect-uuid B07DF049-7AD9-47B5-9F8F-9EE728056398 \
        --stat /pong/init --hash /sbin/launchd.ios
    read-ufs-window-apfs.py --image prepared-os.img --stat /pong/init
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(os.environ.get('APFS_TOOLS') or ROOT / 'tools/apfs')
sys.path.insert(0, str(TOOLS))
TARGET = '/dev/block/by-name/userdata'
BLOCK = 4096


class AdbWindow:
    """A block-aligned reader for one SHNGROOT window, backed by adb."""

    def __init__(self, adb, serial, base, size):
        self.adb = adb
        self.serial = serial
        self.base = base
        self.size = size
        self.path = '<%s window %#x>' % (serial, base)
        self.cache = {}
        self.reads = 0

    def read(self, offset, length):
        if offset < 0 or length < 0 or offset + length > self.size:
            raise IOError('read outside the window')
        start = offset - offset % BLOCK
        end = offset + length
        blocks = (end - start + BLOCK - 1) // BLOCK
        result = bytearray()
        for index in range(blocks):
            addr = start + index * BLOCK
            block = self.cache.get(addr)
            if block is None:
                block = self._block(addr)
                self.cache[addr] = block
            result += block
        return bytes(result[offset - start:offset - start + length])

    def _block(self, offset):
        command = [self.adb, '-s', self.serial, 'exec-out', 'dd', 'if=' + TARGET,
                   'bs=4096', 'skip=%d' % ((self.base + offset) // BLOCK),
                   'count=1', 'status=none']
        result = subprocess.run(command, capture_output=True)
        if result.returncode != 0 or len(result.stdout) != BLOCK:
            raise IOError('device read failed at window offset %#x' % offset)
        self.reads += 1
        return result.stdout

    def close(self):
        self.cache.clear()


def read_directory(adb, serial):
    result = subprocess.run([adb, '-s', serial, 'exec-out', 'dd', 'if=' + TARGET,
                             'bs=4096', 'count=1', 'status=none'], capture_output=True)
    raw = result.stdout
    if len(raw) != 4096 or raw[:8] != b'SHNGROOT':
        raise SystemExit('no SHNGROOT directory at the start of userdata')
    version, count, _total = struct.unpack_from('<IIQ', raw, 8)
    if version != 1:
        raise SystemExit('unsupported SHNGROOT version %d' % version)
    windows = {}
    for i in range(count):
        name, offset, size = struct.unpack_from('<32sQQ', raw, 24 + 128 * i)
        windows[name.split(b'\0')[0].decode('ascii')] = (offset, size)
    return windows


def report(container, image, args):
    import apfs
    print(f'  container UUID {uuid.UUID(bytes=container.nx["uuid"])}, '
          f'block size {container.block_size}, xid {container.xid}')
    volumes = container.volumes()
    if not volumes:
        print('  FAIL: no APFS volume in the container')
        return False
    expected = args.expect_uuid.upper() if args.expect_uuid else None
    matched = expected is None
    volume = volumes[0]
    for candidate in volumes:
        found = apfs._uuid(candidate.vol_uuid).upper()
        print(f'  volume {candidate.volname!r} UUID {found} role {candidate.role:#x} '
              f'sealed={candidate.sealed}')
        if found == expected:
            matched = True
        if args.volume and candidate.volname == args.volume:
            volume = candidate
    if not matched:
        print(f'  FAIL: no volume carries {expected}')
    ok = matched
    for path in args.stat:
        try:
            hit = volume.lookup(path)
        except Exception as error:
            detail = str(error)
            if volume.sealed and 'checksum' in detail:
                detail += '; sealed volume root resolves through a snapshot this reader does not walk'
            print(f'  {path}: unreadable ({detail})')
            ok = False
            continue
        if hit is None:
            print(f'  {path}: MISSING')
            ok = False
            continue
        inode = volume.inode(hit[0])
        kind = 'dir' if inode.is_dir else 'file' if inode.is_reg else \
            'link' if inode.is_link else 'other'
        print(f'  {path}: {kind} mode {oct(inode.mode)} '
              f'owner {inode.owner}:{inode.group} size {inode.size}')
    for path in args.hash:
        try:
            hit = volume.lookup(path)
        except Exception as error:
            detail = str(error)
            if volume.sealed and 'checksum' in detail:
                detail += '; sealed volume root resolves through a snapshot this reader does not walk'
            print(f'  {path}: unreadable ({detail})')
            ok = False
            continue
        if hit is None:
            print(f'  {path}: MISSING')
            ok = False
            continue
        data = volume.inode(hit[0]).contents()
        print(f'  {path}: sha256 {hashlib.sha256(data).hexdigest()} ({len(data)} bytes)')
    reads = getattr(image, 'reads', 0)
    if reads:
        print(f'  {reads} device blocks read')
    print('  PASS' if ok else '  FAIL')
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--serial')
    source.add_argument('--image', type=Path)
    parser.add_argument('--window', help='SHNGROOT window name, with --serial')
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--volume', help='volume name when the container holds several')
    parser.add_argument('--expect-uuid')
    parser.add_argument('--stat', action='append', default=[], metavar='PATH')
    parser.add_argument('--hash', action='append', default=[], metavar='PATH')
    args = parser.parse_args()
    import apfs
    image = None
    try:
        if args.image:
            if not args.image.is_file():
                raise SystemExit(f'image not found: {args.image}')
            print(f'image {args.image}')
            container = apfs.Container(str(args.image))
            try:
                return 0 if report(container, None, args) else 1
            finally:
                container.close()
        if not args.window:
            raise SystemExit('--window is required with --serial')
        adb = shutil.which(args.adb) or args.adb
        windows = read_directory(adb, args.serial)
        if args.window not in windows:
            raise SystemExit(f'window {args.window} not found: {sorted(windows)}')
        offset, size = windows[args.window]
        print(f'{args.window}: offset {offset:#x}, {size} bytes')
        image = AdbWindow(adb, args.serial, offset, size)
        head = image.read(0, 1024)
        if head[512:520] == b'EFI PART':
            from dmg import read_gpt, APFS_PART_TYPE
            parts = [p for p in read_gpt(image) if p.type_guid == APFS_PART_TYPE]
            if len(parts) != 1:
                raise SystemExit(f'expected one APFS partition, found {len(parts)}')
            print(f'  GPT: APFS partition at {parts[0].offset:#x}, {parts[0].length} bytes')
            source_image = apfs.PartitionImage(image, parts[0])
        else:
            source_image = image
        apfs.open_image = lambda path: source_image
        container = apfs.Container(args.window)
        try:
            return 0 if report(container, image, args) else 1
        finally:
            container.close()
    finally:
        if image is not None:
            image.close()


if __name__ == '__main__':
    sys.exit(main())
