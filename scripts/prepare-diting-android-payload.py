#!/usr/bin/env python3
"""Extract a local Android EFI payload from the current Diting capture.
Never accesses a device, changes slots, or produces a flashable boot image.
Private kernel, ramdisks, FDT and boot identifiers remain in the output directory.
"""
import argparse
import json
from pathlib import Path
import struct


def aligned(n, page):
    return (n + page - 1) // page * page


def prepare(capture, output):
    if output.exists():
        raise ValueError('output must not exist')
    receipt = json.loads((capture / 'capture.json').read_text())
    if receipt.get('slot') != '_a' or not receipt.get('read_only'):
        raise ValueError('expected captured active slot A')
    boot = (capture / 'boot_a.img').read_bytes()
    vendor = (capture / 'vendor_boot_a.img').read_bytes()
    if boot[:8] != b'ANDROID!' or struct.unpack_from('<I', boot, 40)[0] != 4:
        raise ValueError('expected boot v4')
    if vendor[:8] != b'VNDRBOOT' or struct.unpack_from('<I', vendor, 8)[0] != 4:
        raise ValueError('expected vendor_boot v4')
    page = struct.unpack_from('<I', vendor, 12)[0]
    if page != 4096:
        raise ValueError('unexpected vendor page size')
    kernel_size, ram_size = struct.unpack_from('<II', boot, 8)
    kernel = boot[4096:4096 + kernel_size]
    ram_start = 4096 + aligned(kernel_size, 4096)
    generic = boot[ram_start:ram_start + ram_size]
    if len(kernel) != kernel_size or len(generic) != ram_size:
        raise ValueError('truncated boot')
    if kernel[:2] != b'MZ' or kernel[56:60] != b'ARM\x64':
        raise ValueError('kernel lacks ARM64 EFI image markers')
    pe = struct.unpack_from('<I', kernel, 60)[0]
    if kernel[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', kernel, pe+4)[0] != 0xaa64:
        raise ValueError('expected AArch64 PE image')
    vendor_size = struct.unpack_from('<I', vendor, 24)[0]
    header_size, dtb_size = struct.unpack_from('<II', vendor, 2096)
    table_size, count, entry_size, static_config_size = struct.unpack_from('<4I', vendor, 2112)
    start = aligned(header_size, page)
    table_start = start + aligned(vendor_size, page) + aligned(dtb_size, page)
    if count != 1 or entry_size != 108 or table_size != count * entry_size:
        raise ValueError('multi-fragment vendor ramdisk needs board-specific selection')
    size, offset, kind = struct.unpack_from('<3I', vendor, table_start)
    if kind not in (0, 1) or offset + size > vendor_size or size != vendor_size:
        raise ValueError('expected one complete normal-boot vendor fragment')
    vendor_ram = vendor[start:start + vendor_size]
    if len(vendor_ram) != vendor_size:
        raise ValueError('truncated vendor ramdisk')
    # Linux bootconfig trailer: pad text, then size, additive checksum, magic.
    config = (capture / 'bootconfig.txt').read_bytes().rstrip(b'\0\n') + b'\n'
    if b'androidboot.slot_suffix = "_a"' not in config:
        raise ValueError('bootconfig does not select captured slot A')
    config += bytes((-len(config)) % 4)
    initrd = vendor_ram + generic + config + struct.pack('<II', len(config), sum(config) & 0xffffffff) + b'#BOOTCONFIG\n'
    dtb = (capture / 'current.dtb').read_bytes()
    if dtb[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I', dtb, 4)[0] != len(dtb):
        raise ValueError('invalid captured FDT')
    cmdline = (capture / 'cmdline.txt').read_text().strip()
    if 'bootconfig' not in cmdline.split():
        raise ValueError('kernel bootconfig argument absent')
    output.mkdir(parents=True)
    for name, data in [('Image.efi', kernel), ('android-initrd.img', initrd), ('android.dtb', dtb), ('cmdline.txt', cmdline.encode())]:
        (output / name).write_bytes(data)
    result = dict(slot='_a', kernel_bytes=len(kernel), initrd_bytes=len(initrd),
                  vendor_ramdisk_fragments=count, vendor_bootconfig_bytes=static_config_size,
                  bootconfig_source='captured running Android', device_tested=False,
                  flashable=False, requires_ram_boot_validation=True)
    (output / 'payload.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.capture, a.output), indent=2))
