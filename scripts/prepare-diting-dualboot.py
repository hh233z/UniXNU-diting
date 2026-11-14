#!/usr/bin/env python3
"""Add a RAM-boot system selector to an existing Diting candidate.

Android uses the existing firmware cold-reset action, returning to the
unchanged active Android slot. This image must NOT be flashed to boot: that
would restart this same menu, not provide an installed Android handoff.
Only the payload menu and its required PONGFAT1 CRC change.
Requires pyfatfs; never writes a device or changes slots.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import tomllib
import zlib

MENU = '/EFI/UniXNU/unixnu.toml'


def make_menu(text, timeout=10):
    original = tomllib.loads(text)
    if original.get('version') != 1:
        raise ValueError('expected UniXNU schema version 1')
    entries = original.get('entry', [])
    xnu = [e for e in entries if e.get('type') == 'xnu']
    if len(xnu) != 1 or 'diting_build=ipados18-22H374' not in xnu[0].get('args', '').split():
        raise ValueError('expected one prepared Diting 22H374 XNU entry')
    if not 1 <= timeout <= 60:
        raise ValueError('timeout must be 1..60 seconds')
    # Preserve every XNU field verbatim, including future nested entry tables.
    blocks = re.split(r'(?m)^\[\[entry\]\]\s*$', text)
    if len(blocks) != len(entries) + 1:
        raise ValueError('ambiguous entry layout')
    header = blocks[0]
    for section in ('boot', 'ui'):
        header = re.sub(r'(?ms)^\[' + section + r'\][^\n]*\n.*?(?=^\[|\Z)', '', header)
    header = header.rstrip() + ('\n[boot]\n' + f'timeout = {timeout}\n' +
               'fallback_timeout = 10\nrotate = 0\ndefault = "android"\n' +
               '[ui]\ntitle = "Diting Dual Boot - RAM test"\nlayout = "portrait"\nlogo = false\n')
    out = header + '''
[[entry]]
id = "android"
title = "Android - restart to installed system"
type = "action"
action = "reset"
'''
    for entry, block in zip(entries, blocks[1:]):
        if entry.get('type') == 'xnu':
            out += '\n[[entry]]\n' + block.strip('\r\n') + '\n'
    out += '''
[[entry]]
id = "tools"
title = "Tools and firmware logs"
type = "action"
action = "tools"
'''
    result = tomllib.loads(out)
    if [e for e in result['entry'] if e.get('type') == 'xnu'] != xnu:
        raise ValueError('XNU configuration changed')
    return out


def prepare(source, output, timeout):
    from pyfatfs.PyFatFS import PyFatFS
    source, output = source.resolve(), output.resolve()
    if source == output or output.exists():
        raise ValueError('output must be a new local file, distinct from source')
    with source.open('rb') as f:
        h = f.read(4096)
        if h[:8] != b'ANDROID!' or struct.unpack_from('<I', h, 40)[0] not in (3, 4):
            raise ValueError('expected Android boot v3/v4 candidate')
        kernel_size, ramdisk_size = struct.unpack_from('<II', h, 8)
        offset = 4096 + (kernel_size + 4095) // 4096 * 4096
        f.seek(offset)
        envelope = f.read(32)
        if envelope[:8] != b'PONGFAT1':
            raise ValueError('missing payload envelope')
        head, size = struct.unpack_from('<IQ', envelope, 12)
        if head < 32 or head % 512 or size < 512 or size % 512 or head + size > ramdisk_size:
            raise ValueError('invalid payload bounds')
        if offset + ramdisk_size > source.stat().st_size:
            raise ValueError('truncated candidate')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    fs = PyFatFS(str(output), offset=offset + head, read_only=False)
    try:
        menu = make_menu(fs.readtext(MENU), timeout)
        # pyfatfs replacement requires removing the old directory entry.
        fs.remove(MENU)
        fs.writebytes(MENU, menu.encode('utf-8'))
    finally:
        fs.close()
    # Format integrity, not a whole-image hash or device readback.
    with output.open('r+b') as f:
        f.seek(offset + head)
        left, crc = size, 0
        while left:
            part = f.read(min(left, 1024 * 1024))
            if not part:
                raise ValueError('truncated FAT')
            crc = zlib.crc32(part, crc)
            left -= len(part)
        f.seek(offset + 24)
        f.write(struct.pack('<I', crc))
    receipt = dict(source=str(source), candidate=str(output), device='diting',
                   mode='temporary-fastboot-boot-only', default='android', timeout=timeout,
                   android_handoff='existing firmware cold reset to unchanged active slot',
                   xnu_entry_preserved=True, device_tested=False, touch_menu_supported=False,
                   permanent_install_supported=False, partition_writes=False)
    output.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.timeout), indent=2))
