#!/usr/bin/env python3
"""Print the APFS volumes a raw container holds, with their UUIDs.

The kernel mounts the root volume by UUID (`root_match_volume_uuid` in the ADT), so a port has to
know the UUID the restore actually carries. This reads a raw APFS container (the .dmg files of an
IPSW are raw containers once decrypted) and lists every volume superblock it finds.

Field offsets come from apfsprogs (`include/apfs/raw.h`): the volume magic sits at 32, the volume
UUID at 0xF0 and the volume name at 0x2C0 of an APSB block.

Usage:
    apfs-volume-uuid.py <container> [<container> ...]
"""
import sys
import uuid
from pathlib import Path

BLOCK = 4096
MAGIC_AT = 32
UUID_AT = 0xF0
NAME_AT = 0x2C0
NAME_LEN = 256
CHUNK = 8 << 20


def scan(path):
    found = []
    with path.open('rb') as handle:
        base = 0
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            at = chunk.find(b'APSB')
            while at >= 0:
                block = base + at - MAGIC_AT
                if block % BLOCK == 0:
                    start = at - MAGIC_AT
                    head = chunk[start:start + BLOCK]
                    if len(head) < BLOCK:
                        head += handle.read(BLOCK - len(head))
                    found.append((block, head))
                at = chunk.find(b'APSB', at + 1)
            base += len(chunk)
    return found


def container_uuid(path):
    with path.open('rb') as handle:
        head = handle.read(BLOCK)
    if head[MAGIC_AT:MAGIC_AT + 4] != b'NXSB':
        return None
    return uuid.UUID(bytes=head[64:80])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for name in sys.argv[1:]:
        path = Path(name)
        container = container_uuid(path)
        print(f'{path.name}: container {container} ({path.stat().st_size} bytes)')
        volumes = scan(path)
        if not volumes:
            print('  no volume superblock found')
        for block, head in volumes:
            raw = head[UUID_AT:UUID_AT + 16]
            label = head[NAME_AT:NAME_AT + NAME_LEN].split(b'\0')[0].decode('utf-8', 'replace')
            try:
                vol = uuid.UUID(bytes=raw)
            except ValueError:
                vol = 'not a UUID'
            print(f'  block {block // BLOCK:<10} uuid {vol}  name {label!r}')


if __name__ == '__main__':
    main()