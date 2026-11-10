#!/usr/bin/env python3
"""Gate the one-way diting boot: check device, windows, UUIDs and kernel args.

`fastboot boot` on this phone leaves it running the payload until a person power
cycles it, so every avoidable failure is caught here first. The gate reads only:
device state, the 4 KiB SHNGROOT directory with sampled 64 KiB regions, the APFS
volume markers of all three windows, the boot image digest and its embedded
kernel arguments. It writes nothing and does not boot.

Run on the host (Windows) where adb lives; the APFS helpers are imported from
the device repository's tools/apfs.

Usage:
    preflight-diting-boot.py --serial 9e0c2b55 \
        --boot-image ../build-work/greenI2/.../boot/pong-unixnu-uefi.img \
        --os ../build-work/prepared-420734-os.img \
        --data ../build-work/windows/Data.img
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
DEFAULTS = dict(
    os='B07DF049-7AD9-47B5-9F8F-9EE728056398',
    systemos='4A77BA00-2826-44C4-B883-1FA92AC36880',
    data='337CF716-F62B-446B-B959-4A5F12A7701C',
)


def run(command, env=None):
    result = subprocess.run(command, capture_output=True, text=True,
                            cwd=str(ROOT), env=env)
    return result.returncode == 0, result.stdout + result.stderr


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b''):
            result.update(chunk)
    return result.hexdigest()


def kernel_args(image):
    data = image.read_bytes()
    at = data.find(b'-v keepsyms')
    if at < 0:
        at = data.find(b'keepsyms=1')
    if at < 0:
        return None
    ends = [x for x in (data.find(b'\0', at), data.find(b'"', at)) if x > at]
    end = min(ends) if ends else at + 1200
    return data[at:end].decode('latin1')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--boot-image', type=Path, required=True)
    parser.add_argument('--os', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--systemos-uuid', default=DEFAULTS['systemos'])
    parser.add_argument('--os-uuid', default=DEFAULTS['os'])
    parser.add_argument('--data-uuid', default=DEFAULTS['data'])
    parser.add_argument('--expect-boot-sha', default='C5D58F80')
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--skip-window-samples', action='store_true',
                        help='only run the metadata checks (faster)')
    args = parser.parse_args()
    adb = shutil.which(args.adb) or args.adb
    env = dict(os.environ)
    env.setdefault('APFS_TOOLS', str(ROOT / 'tools' / 'apfs'))
    failures = []

    def record(name, ok, output=''):
        print(('PASS ' if ok else 'FAIL ') + name)
        if not ok:
            failures.append(name)
            if output:
                print('\n'.join('    ' + line for line in output.strip().splitlines()[-12:]))

    for path, label in ((args.boot_image, '--boot-image'), (args.os, '--os'),
                        (args.data, '--data')):
        if not path.is_file():
            raise SystemExit(f'{label} not found: {path}')

    ok, out = run([adb, '-s', args.serial, 'get-state'])
    record(f'device {args.serial} reachable: {out.strip()}', ok and 'recovery' in out, out)
    ok, out = run([adb, '-s', args.serial, 'shell', 'getprop', 'ro.product.device'])
    record(f'product is diting: {out.strip()}', ok and out.strip() == 'diting', out)

    boot_sha = digest(args.boot_image)
    record(f'boot image sha256 {boot_sha[:16]}… matches {args.expect_boot_sha}',
           boot_sha.upper().startswith(args.expect_boot_sha.upper()), boot_sha)
    arguments = kernel_args(args.boot_image)
    if arguments is None:
        record('kernel arguments line found in the image', False)
    else:
        print('    args: ' + arguments)
        record('args keep pong_ufs_readwrite=1', 'pong_ufs_readwrite=1' in arguments)
        record('args do not set pong_init_path', 'pong_init_path=' not in arguments)

    if not args.skip_window_samples:
        for window, image in (('OS', args.os), ('Data', args.data)):
            ok, out = run([sys.executable, str(SCRIPTS / 'verify-ufs-window.py'),
                           '--serial', args.serial, '--window', window,
                           '--image', str(image), '--samples', str(args.samples),
                           '--adb', adb])
            record(f'{window} window matches {image.name} ({args.samples} samples)', ok, out)

    for window, expected in (('OS', args.os_uuid), ('SystemOS', args.systemos_uuid),
                             ('Data', args.data_uuid)):
        ok, out = run([sys.executable, str(SCRIPTS / 'read-ufs-window-apfs.py'),
                       '--serial', args.serial, '--window', window,
                       '--expect-uuid', expected, '--adb', adb], env=env)
        record(f'{window} APFS volume UUID {expected}', ok, out)

    print()
    if failures:
        print(f'{len(failures)} check(s) failed; do not boot yet.')
        return 1
    print('All checks passed. Boot with:')
    print(f'  {adb} -s {args.serial} reboot bootloader')
    print(f'  fastboot -s {args.serial} boot "{args.boot_image}"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
