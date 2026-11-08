#!/usr/bin/env python3
"""Convert a raw partition image to the Android sparse format fastboot streams.

Why: a 32-bit fastboot cannot flash a 10 GiB raw image (it aborts with std::bad_alloc), and
writing the partition from a running Android lets f2fs rewrite the first blocks on shutdown,
which destroys a manifest stored there. fastboot's sparse path transfers chunk by chunk, so the
image can be written from the bootloader instead.

Format: 28-byte file header, then 12-byte chunk headers with raw (0xCAC1) data chunks.

Usage:
    make-sparse-image.py <raw image> <output.img> [--chunk-mib 16]
"""
import argparse
import struct
import sys
from pathlib import Path

MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
BLOCK = 4096


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--chunk-mib', type=int, default=16)
    args = parser.parse_args()
    size = args.source.stat().st_size
    if size % BLOCK:
        raise SystemExit(f'{args.source} is not a multiple of {BLOCK} bytes')
    total_blocks = size // BLOCK
    blocks_per_chunk = max(1, (args.chunk_mib << 20) // BLOCK)
    chunks = (total_blocks + blocks_per_chunk - 1) // blocks_per_chunk
    with args.source.open('rb') as src, args.output.open('wb') as out:
        out.write(struct.pack('<IHHHHIIII', MAGIC, 1, 0, 28, 12, BLOCK,
                              total_blocks, chunks, 0))
        done = 0
        while done < total_blocks:
            count = min(blocks_per_chunk, total_blocks - done)
            data = src.read(count * BLOCK)
            if len(data) != count * BLOCK:
                raise SystemExit(f'short read at block {done}')
            out.write(struct.pack('<HHII', CHUNK_RAW, 0, count, 12 + len(data)))
            out.write(data)
            done += count
    print(f'{args.source} -> {args.output}: {total_blocks} blocks, {chunks} chunks, '
          f'{args.output.stat().st_size} bytes', file=sys.stderr)


if __name__ == '__main__':
    main()