#!/usr/bin/env python3
"""Write the prepared userdata image from the bootloader and boot a payload.

The 32-bit fastboot on the bench host cannot flash the 10 GiB raw image (std::bad_alloc), and
writing it from a running Android is unsafe: f2fs writes its superblock at offset 1024 inside the
SHNGROOT block when the device shuts down, so the next boot reads the magic but fails the header
hash (`manifest=3` in the UFS report). fastboot streams the sparse encoding chunk by chunk, so the
write happens with Android out of the picture entirely.

Usage:
    flash-userdata-image.py --image out/userdata/userdata-root.img [--boot boot/diting-unixnu-uefi.img]

The device must already be in the bootloader. The script refuses to continue when the product or the
unlock state is not what the board expects.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, check=True):
    print('+', ' '.join(str(part) for part in command), flush=True)
    result = subprocess.run([str(part) for part in command], text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if check and result.returncode:
        raise SystemExit(f'command failed ({result.returncode}): {command[0]}')
    return result


def getvar(fastboot, name):
    result = run([fastboot, 'getvar', name], check=False)
    text = (result.stdout or '') + (result.stderr or '')
    for line in text.splitlines():
        if line.lower().startswith(name.lower() + ':'):
            return line.split(':', 1)[1].strip()
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True, help='raw userdata image')
    parser.add_argument('--sparse', type=Path, help='reuse or write this sparse encoding')
    parser.add_argument('--boot', type=Path, help='payload image to boot after flashing')
    parser.add_argument('--product', default='diting')
    parser.add_argument('--adb', default=shutil.which('adb') or 'adb')
    parser.add_argument('--fastboot', default=shutil.which('fastboot') or 'fastboot')
    args = parser.parse_args()

    if not args.image.is_file():
        raise SystemExit(f'{args.image} missing')
    sparse = args.sparse or args.image.with_suffix('.sparse.img')
    if not sparse.is_file():
        run([sys.executable, ROOT / 'scripts/make-sparse-image.py', args.image, sparse])

    devices = run([args.fastboot, 'devices'], check=False).stdout.split()
    if not devices:
        raise SystemExit('no fastboot device: put the phone in the bootloader first')
    product = getvar(args.fastboot, 'product')
    unlocked = getvar(args.fastboot, 'unlocked')
    print(f'product={product} unlocked={unlocked}', flush=True)
    if product and product != args.product:
        raise SystemExit(f'refusing: product is {product}, expected {args.product}')
    if unlocked and unlocked.lower() not in ('yes', 'true', '1'):
        raise SystemExit(f'refusing: bootloader reports unlocked={unlocked}')

    run([args.fastboot, 'flash', 'userdata', sparse])
    print('userdata written from the bootloader', flush=True)
    if args.boot:
        run([args.fastboot, 'boot', args.boot])
        print('payload booted; read the panel and the ramoops dump on the next boot', flush=True)


if __name__ == '__main__':
    main()