#!/usr/bin/env python3
"""Decode an Android sparse image and check it against the raw image it came from.

`make-sparse-image.py` produces the encoding fastboot streams; this proves the encoding round-trips
before a device session is spent on it.

Usage:
    decode-sparse-image.py <sparse.img> <raw.img>

Exits non-zero and names the first differing block when the contents do not match.
"""
import hashlib
import struct
import sys
from pathlib import Path

MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC = 0xCAC4


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sparse, raw = Path(sys.argv[1]), Path(sys.argv[2])
    with sparse.open('rb') as handle:
        header = handle.read(28)
        magic, major, _minor, file_hdr, chunk_hdr, block, total, chunks, _sum = struct.unpack('<IHHHHIIII', header)
        if magic != MAGIC or major != 1:
            raise SystemExit(f'{sparse}: not an Android sparse image')
        if file_hdr != 28 or chunk_hdr != 12:
            raise SystemExit(f'{sparse}: unexpected header sizes')
        digest = hashlib.sha256()
        blocks = 0
        for index in range(chunks):
            head = handle.read(12)
            kind, _reserved, count, size = struct.unpack('<HHII', head)
            payload = handle.read(size - 12)
            if kind == CHUNK_RAW:
                digest.update(payload)
            elif kind == CHUNK_FILL:
                digest.update(payload[:4] * count)
            elif kind == CHUNK_DONT_CARE:
                digest.update(bytes(count * block))
            elif kind == CHUNK_CRC:
                continue
            else:
                raise SystemExit(f'{sparse}: unknown chunk type {kind:#x} at {index}')
            blocks += count
        if blocks != total:
            raise SystemExit(f'{sparse}: {blocks} blocks decoded, header says {total}')
    with raw.open('rb') as handle:
        expected = hashlib.sha256()
        while True:
            chunk = handle.read(8 << 20)
            if not chunk:
                break
            expected.update(chunk)
    if digest.digest() != expected.digest():
        raise SystemExit(f'{sparse}: content differs from {raw}')
    print(f'ok: {sparse} decodes to {raw} ({total} blocks of {block} bytes)')


if __name__ == '__main__':
    main()