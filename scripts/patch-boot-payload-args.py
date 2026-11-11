#!/usr/bin/env python3
"""Add or replace kernel boot arguments in an existing UniXNU boot image.

The payload embeds the arguments three times: the xnu menu entry in
EFI/UniXNU/unixnu.toml, the development boot manifest next to the kernel, and
the manifest's SHA-384 in the ADT (chosen/boot-manifest-hash). The PONGFAT1
envelope also carries a CRC32 of the payload FAT. Changing one copy only makes
the boot refuse or keeps the old argument, so this rewrites all of them and the
envelope CRC, then puts the payload back into the same ramdisk slot.

The FAT files are edited with mtools; the tool runs where mcopy/mdel exist
(WSL). No partition is touched and the kernel, ADT tree and firmware volume are
not rebuilt.

Usage:
    patch-boot-payload-args.py --image pong-unixnu-uefi.img \
        --output pong-unixnu-uefi-cache.img --set launchd_unsecure_cache=1
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

FAT_PATH = '::/EFI/UniXNU/unixnu.toml'
MANIFEST_PATH = '::/EFI/UniXNU/Payloads/pong-boot-manifest.json'
ADT_PATH = '::/EFI/UniXNU/Payloads/kernel.macho.adt'


def align(value, size=4096):
    return (value + size - 1) // size * size


def mtools(env, *args):
    result = subprocess.run(list(args), capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise SystemExit('%s failed: %s' % (args[0], result.stderr.strip()))


def extract(image, env, work):
    magic = image[:8]
    if magic != b'ANDROID!':
        raise SystemExit('not an Android boot image')
    kernel_size, ramdisk_size = struct.unpack_from('<2I', image, 8)
    header_size, = struct.unpack_from('<I', image, 20)
    offset = align(header_size) + align(kernel_size)
    envelope = image[offset:offset + ramdisk_size]
    tag, version, head_len, fat_len, crc, flags = struct.unpack_from('<8sIIQII', envelope, 0)
    if tag != b'PONGFAT1' or version != 1 or head_len != 4096:
        raise SystemExit('the ramdisk is not a PONGFAT1 envelope')
    fat = envelope[head_len:head_len + fat_len]
    if zlib.crc32(fat) != crc:
        raise SystemExit('the payload FAT CRC does not match the envelope')
    fat_file = Path(work) / 'payload-fat.img'
    fat_file.write_bytes(fat)
    mtools(env, 'mcopy', '-i', str(fat_file), FAT_PATH, str(Path(work) / 'unixnu.toml'))
    mtools(env, 'mcopy', '-i', str(fat_file), MANIFEST_PATH, str(Path(work) / 'manifest.json'))
    mtools(env, 'mcopy', '-i', str(fat_file), ADT_PATH, str(Path(work) / 'kernel.adt'))
    return dict(offset=offset, ramdisk_size=ramdisk_size, fat_file=fat_file,
                fat_len=fat_len, envelope_size=len(envelope))


def apply_args(toml_text, manifest, sets):
    lines = toml_text.splitlines(keepends=True)
    args_line = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith('args = "'):
            args_line = index
            break
    if args_line is None:
        raise SystemExit('the xnu entry has no args line')
    line = lines[args_line]
    prefix, _, rest = line.partition('args = "')
    value, _, suffix = rest.partition('"')
    tokens = value.split(' ')
    for item in sets:
        name, _, assigned = item.partition('=')
        if not name:
            raise SystemExit('empty argument name')
        replaced = False
        for token_index, token in enumerate(tokens):
            if token.partition('=')[0] == name:
                tokens[token_index] = item
                replaced = True
                break
        if not replaced:
            tokens.append(item)
    arguments = ' '.join(tokens)
    lines[args_line] = prefix + 'args = "' + arguments + '"' + suffix
    toml_text = ''.join(lines)
    manifest['boot_args'] = arguments
    return toml_text, manifest, arguments


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--set', action='append', default=[], metavar='NAME=VALUE')
    args = parser.parse_args()
    image = args.image.read_bytes()
    env = dict(os.environ, MTOOLS_SKIP_CHECK='1')
    with tempfile.TemporaryDirectory() as work:
        info = extract(image, env, work)
        toml_path = Path(work) / 'unixnu.toml'
        manifest_path = Path(work) / 'manifest.json'
        adt_path = Path(work) / 'kernel.adt'
        toml_text, manifest, arguments = apply_args(
            toml_path.read_text(), json.loads(manifest_path.read_text()), args.set)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False,
                                    separators=(',', ':')).encode()
        digest = hashlib.sha384(manifest_bytes).digest()
        adt = bytearray(adt_path.read_bytes())
        at = adt.find(b'boot-manifest-hash')
        if at < 0 or at + 32 + 4 + 48 > len(adt):
            raise SystemExit('the ADT has no boot-manifest-hash property')
        length, = struct.unpack_from('<I', adt, at + 32)
        if length != 48:
            raise SystemExit('unexpected boot-manifest-hash length %d' % length)
        adt[at + 36:at + 36 + 48] = digest
        toml_path.write_text(toml_text)
        manifest_path.write_bytes(manifest_bytes)
        adt_path.write_bytes(adt)
        fat_file = info['fat_file']
        for source, target in ((toml_path, FAT_PATH), (manifest_path, MANIFEST_PATH),
                               (adt_path, ADT_PATH)):
            mtools(env, 'mdel', '-i', str(fat_file), target)
            mtools(env, 'mcopy', '-i', str(fat_file), str(source), target)
        fat = fat_file.read_bytes()
        if len(fat) != info['fat_len']:
            raise SystemExit('the FAT changed size; refusing to repack')
        header = bytearray(4096)
        struct.pack_into('<8sIIQII', header, 0, b'PONGFAT1', 1, 4096, len(fat),
                         zlib.crc32(fat), 0)
        envelope = bytes(header) + fat
        if len(envelope) != info['ramdisk_size']:
            raise SystemExit('the envelope size changed; refusing to repack')
        output = bytearray(image)
        start = info['offset']
        output[start:start + len(envelope)] = envelope
        args.output.write_bytes(output)
        print('args:', arguments)
        print('manifest sha384:', digest.hex())
        print('wrote', args.output, len(output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
