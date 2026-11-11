#!/usr/bin/env python3
"""Check a prepared 22H374 userland triple against what bring-up needs.

Reads the OS, Data and (optionally) SystemOS window sources with the in-tree APFS
reader and reports the items phase 6 depends on.

The prepared userland puts a copy of the Diting static init at /sbin/launchd and
keeps Apple's launchd as /sbin/launchd.ios, so the kernel's native init path runs
the Diting init (Data seed, preferences, environment) and that init execs the real
launchd. The Data volume is the data partition: its root is /private/var, so the
seed entries (tmp, keybags, mobile, db) sit at the volume root.

The images may be bare APFS containers or a GPT with one APFS partition, the two
shapes the UFS windows accept. Read-only: no device is touched and no image is
hashed. Use --expect-*-uuid to pin the UUIDs the kernel was built with.

Usage:
    inspect-diting-userland.py --os OS.img --data Data.img [--systemos S.img]
        [--expect-os-uuid UUID] [--expect-data-uuid UUID]
        [--expect-systemos-uuid UUID]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/apfs'))


def fail(message):
    print('FAIL: ' + message)
    return False


def open_volume(path):
    import apfs
    container = apfs.Container(str(path))
    volumes = container.volumes()
    if not volumes:
        container.close()
        raise SystemExit(f'{path}: no APFS volume')
    return container, volumes[0]


def kind_of(path):
    with path.open('rb') as handle:
        head = handle.read(1024)
    if head[32:36] == b'NXSB':
        return 'bare APFS container'
    if head[512:520] == b'EFI PART':
        return 'GPT with one APFS partition'
    raise SystemExit(f'{path}: neither a bare APFS container nor a GPT')


def entry_at(volume, path):
    hit = volume.lookup(path)
    return None if hit is None else volume.inode(hit[0])


def launchd_flags(contents):
    """PerformInRestore presence next to each embedded boot-task name."""
    found = {}
    for task in (b'usermanagerd', b'launchd_cache_loader'):
        at = contents.find(task)
        flags = []
        while at >= 0:
            window = contents[max(0, at - 2048):at + 2048]
            flags.append(b'PerformInRestore' in window)
            at = contents.find(task, at + 1)
        found[task.decode()] = flags
    return found


def check_os(path, expect_uuid):
    import apfs
    ok = True
    container, volume = open_volume(path)
    try:
        found = apfs._uuid(volume.vol_uuid).upper()
        print(f'OS {path}: {kind_of(path)}, volume {volume.volname!r} UUID {found}')
        if expect_uuid and found != expect_uuid:
            ok = fail(f'OS UUID {found} != expected {expect_uuid}')
        init = entry_at(volume, '/diting/init')
        if init is None or not init.is_reg:
            ok = fail('OS /diting/init missing or not a regular file')
        elif not init.mode & 0o111:
            ok = fail(f'OS /diting/init mode {oct(init.mode)} is not executable')
        else:
            print(f'  /diting/init mode {oct(init.mode)} size {init.size}')
        for name in ('/diting/etc/var.skel', '/diting/var-seed'):
            inode = entry_at(volume, name)
            if inode is None or not (inode.is_reg or inode.is_dir):
                ok = fail(f'OS {name} missing')
            else:
                print(f'  {name} {"dir" if inode.is_dir else "file"} present')
        if entry_at(volume, '/private/var') is None:
            ok = fail('OS /private/var missing')
        system_launchd = entry_at(volume, '/sbin/launchd')
        apple_launchd = entry_at(volume, '/sbin/launchd.ios')
        if apple_launchd is not None:
            if system_launchd is None or init is None:
                ok = fail('/sbin/launchd.ios exists but the wrapper contract is incomplete')
            else:
                same = system_launchd.contents() == init.contents()
                print(f'  /sbin/launchd wrapper identical to /diting/init: {same}')
                if not same:
                    ok = fail('/sbin/launchd is not the Diting init wrapper')
            target = apple_launchd
        else:
            target = system_launchd
        if target is None:
            ok = fail('OS has neither /sbin/launchd nor /sbin/launchd.ios')
        else:
            flags = launchd_flags(target.contents())
            for task, seen in flags.items():
                print(f'  launchd {task}: PerformInRestore={seen}')
                if not any(seen):
                    print(f'  note: {task} is not a restore-mode task in this launchd')
    finally:
        container.close()
    return ok


def check_systemos(path, expect_uuid):
    import apfs
    ok = True
    container, volume = open_volume(path)
    try:
        found = apfs._uuid(volume.vol_uuid).upper()
        print(f'SystemOS {path}: {kind_of(path)}, volume {volume.volname!r} UUID {found}')
        if expect_uuid and found != expect_uuid:
            ok = fail(f'SystemOS UUID {found} != expected {expect_uuid}')
        try:
            trampolines = entry_at(volume, '/usr/lib/libobjc-trampolines.dylib')
        except Exception as error:
            print(f'  /usr/lib/libobjc-trampolines.dylib: skipped, volume tree unreadable '
                  f'({error})')
            trampolines = None
        else:
            if trampolines is None:
                ok = fail('SystemOS /usr/lib/libobjc-trampolines.dylib missing')
            else:
                print('  /usr/lib/libobjc-trampolines.dylib present')
    finally:
        container.close()
    return ok


def check_data(path, expect_uuid):
    """The Data volume root is the mounted /private/var."""
    import apfs
    ok = True
    container, volume = open_volume(path)
    try:
        found = apfs._uuid(volume.vol_uuid).upper()
        print(f'Data {path}: {kind_of(path)}, volume {volume.volname!r} UUID {found}')
        if expect_uuid and found != expect_uuid:
            ok = fail(f'Data UUID {found} != expected {expect_uuid}')
        marker = entry_at(volume, '/.diting-data-22H374')
        if marker is None:
            ok = fail('Data /.diting-data-22H374 marker missing')
        else:
            print(f'  seed marker: {marker.contents().strip().decode("ascii", "replace")}')
        for name in ('/keybags', '/mobile', '/db', '/containers', '/preferences'):
            inode = entry_at(volume, name)
            if inode is None or not inode.is_dir:
                ok = fail(f'Data {name} missing or not a directory')
            else:
                print(f'  {name} dir mode {oct(inode.mode)}')
        tmp = entry_at(volume, '/tmp')
        if tmp is None or not tmp.is_dir:
            ok = fail('Data /tmp missing or not a directory')
        else:
            print(f'  /tmp dir mode {oct(tmp.mode)}')
            if tmp.mode & 0o777 != 0o777 or not tmp.mode & 0o1000:
                ok = fail('Data /tmp is not mode 01777')
    finally:
        container.close()
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--os', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--systemos', type=Path)
    parser.add_argument('--expect-os-uuid')
    parser.add_argument('--expect-systemos-uuid')
    parser.add_argument('--expect-data-uuid')
    args = parser.parse_args()
    for name in ('os', 'data', 'systemos'):
        path = getattr(args, name)
        if path is not None and not path.is_file():
            raise SystemExit(f'--{name} not found: {path}')
    ok = check_os(args.os, args.expect_os_uuid and args.expect_os_uuid.upper())
    if args.systemos:
        ok = check_systemos(args.systemos, args.expect_systemos_uuid and
                            args.expect_systemos_uuid.upper()) and ok
    ok = check_data(args.data, args.expect_data_uuid and args.expect_data_uuid.upper()) and ok
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
