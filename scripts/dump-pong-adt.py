#!/usr/bin/env python3
"""Print the Apple device tree (ADT) blobs a payload carries.

DarwinBoot loads a <kernel>.adt blob; diagnosing a handoff means reading that tree the way the
kernel will. The format is a plain recursive node encoding:

    u32 property_count, u32 child_count,
    then per property: char key[32], u32 length, data padded to four bytes,
    then the children, back to back.

Blobs are located by finding a root node's own name property and parsing backwards, so no FAT or
container layout has to be understood. A payload can hold more than one blob; --all lists them.

Usage:
    dump-pong-adt.py <image> [--root device-tree] [--all] [--path /device-tree/arm-io/ufshc]
"""
import argparse
import struct
import sys
from pathlib import Path


def parse_node(blob, at):
    if at + 8 > len(blob):
        raise ValueError('truncated node header')
    nprops, nchild = struct.unpack_from('<II', blob, at)
    if nprops > 4096 or nchild > 4096:
        raise ValueError('implausible node counts')
    at += 8
    props = []
    for _ in range(nprops):
        if at + 36 > len(blob):
            raise ValueError('truncated property')
        key = blob[at:at + 32].split(b'\0')[0].decode('latin1')
        (length,) = struct.unpack_from('<I', blob, at + 32)
        at += 36
        if length > len(blob) - at:
            raise ValueError('property longer than the blob')
        data = blob[at:at + length]
        at += length + (4 - length % 4) % 4
        props.append((key, data))
    children = []
    for _ in range(nchild):
        child, at = parse_node(blob, at)
        children.append(child)
    name = dict(props).get('name', b'').split(b'\0')[0].decode('latin1')
    return (name, props, children), at


def find_roots(image, name):
    pattern = b'name' + bytes(28) + struct.pack('<I', len(name) + 1) + name.encode() + b'\0'
    found = []
    start = 0
    while True:
        at = image.find(pattern, start)
        if at < 0:
            return found
        start = at + 1
        node_at = at - 8
        if node_at < 0:
            continue
        try:
            node, end = parse_node(image, node_at)
        except ValueError:
            continue
        if node[0] == name:
            found.append((node, node_at, end))


def fmt(key, data):
    if key in ('compatible', 'name', 'device_type', 'model', 'reg-names', 'clock-names'):
        return ' '.join(part.decode('latin1') for part in data.split(b'\0') if part)
    if len(data) in (1, 2, 4, 8):
        return f'{int.from_bytes(data, "little"):#x}'
    if len(data) % 4 == 0 and len(data) <= 32:
        values = struct.unpack(f'<{len(data) // 4}I', data)
        return ' '.join(f'{value:#x}' for value in values)
    text = data.split(b'\0')[0]
    if text and all(0x20 <= byte < 0x7f for byte in text):
        return '"' + text.decode() + '"'
    return f'{len(data)} bytes'


def walk(node, path, wanted, out):
    here = f'{path}/{node[0]}'
    if wanted is None or here.startswith(wanted):
        out.append(here)
        for key, data in node[1]:
            out.append(f'    {key}: {fmt(key, data)}')
    for child in node[2]:
        walk(child, here, wanted, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--root', default='device-tree')
    parser.add_argument('--path', help='only print this subtree')
    parser.add_argument('--all', action='store_true', help='list every blob found')
    parser.add_argument('--index', type=int, default=0, help='which blob to print with --path')
    args = parser.parse_args()
    image = args.image.read_bytes()
    roots = find_roots(image, args.root)
    if not roots:
        raise SystemExit(f'no ADT root named {args.root!r} in {args.image}')
    if args.all:
        for index, (node, offset, end) in enumerate(roots):
            print(f'[{index}] {offset:#x} {end - offset} bytes {len(node[2])} top-level nodes')
        return
    node, offset, end = roots[args.index]
    print(f'ADT at {offset:#x}, {end - offset} bytes, {len(node[2])} top-level nodes', file=sys.stderr)
    out = []
    walk(node, '', args.path, out)
    print('\n'.join(out))


if __name__ == '__main__':
    main()