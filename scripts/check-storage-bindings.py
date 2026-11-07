#!/usr/bin/env python3
"""检查最终 arm64 Mach-O 内核的存储绑定是否落在映射段中。"""
import argparse
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


REQUIRED = {
    '__ZN20IOBlockStorageDevice10gMetaClassE',
    '__ZTV20IOBlockStorageDevice',
}


def inspect(data):
    if len(data) < 32 or struct.unpack_from('<I', data)[0] != 0xfeedfacf:
        raise ValueError('需要未压缩的 64 位 Mach-O 内核')
    count, command_bytes = struct.unpack_from('<II', data, 16)
    end = 32 + command_bytes
    if end > len(data):
        raise ValueError('Mach-O 加载命令超出文件')
    segments = []
    symtab = None
    prelink_info_data = None
    pos = 32
    for _ in range(count):
        if pos + 8 > end:
            raise ValueError('Mach-O 加载命令截断')
        command, size = struct.unpack_from('<II', data, pos)
        if size < 8 or pos + size > end:
            raise ValueError('Mach-O 加载命令长度无效')
        if command == 0x19:
            if size < 72:
                raise ValueError('Mach-O 段命令截断')
            name, address, length, fileoff, filesize, _, protection = struct.unpack_from('<16sQQQQII', data, pos + 8)
            if length:
                segments.append((address, address + length, protection, name.rstrip(b'\0').decode('ascii')))
            if name.rstrip(b'\0') == b'__PRELINK_INFO':
                if fileoff + filesize > len(data):
                    raise ValueError('预链接信息超出文件')
                prelink_info_data = data[fileoff:fileoff + filesize].split(b'\0', 1)[0]
        elif command == 2:
            if size < 24 or symtab is not None:
                raise ValueError('Mach-O 符号表无效')
            symtab = struct.unpack_from('<IIII', data, pos + 8)
        pos += size
    if pos != end or symtab is None:
        raise ValueError('缺少符号表或加载命令大小不一致')
    symoff, nsyms, stroff, strsize = symtab
    if symoff + nsyms * 16 > len(data) or stroff + strsize > len(data):
        raise ValueError('Mach-O 符号表超出文件')
    found = {}
    for i in range(nsyms):
        index, kind, _, _, value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
        if not index or index >= strsize or kind & 0xe0 or kind & 0x0e != 2:
            continue
        start = stroff + index
        stop = data.find(b'\0', start, stroff + strsize)
        if stop < 0:
            raise ValueError('Mach-O 符号名未终止')
        name = data[start:stop].decode('utf-8', errors='replace')
        if name in REQUIRED or name.startswith(('__ZN20IOBlockStorageDevice', '__ZNK20IOBlockStorageDevice')):
            found[name] = value
    missing = REQUIRED - found.keys()
    if missing:
        raise ValueError('缺少存储绑定：' + ', '.join(sorted(missing)))
    failures = []
    prelink_info = next((s for s in segments if s[3] == '__PRELINK_INFO'), None)
    prelink_segments = [s for s in segments if s[3] in
                        ('__PRELINK_TEXT', '__PLK_TEXT_EXEC', '__PLK_DATA_CONST', '__PRELINK_DATA')]
    if prelink_info is None or not prelink_segments:
        raise ValueError('缺少预链接段或预链接信息段')
    if any(segment[1] > prelink_info[0] for segment in prelink_segments):
        failures.append('__PRELINK_INFO 不在所有预链接段之后，内核静态地址上界可能截断组件')
    try:
        root = ET.fromstring(prelink_info_data)
    except (TypeError, ET.ParseError) as exc:
        raise ValueError('无法解析预链接信息') from exc
    for element in root.iter('dict'):
        children = list(element)
        if any(children[i].tag == 'key' and children[i].text == 'IOClass' and
               children[i + 1].tag == 'string' and children[i + 1].text == 'AppleARMCPU'
               for i in range(len(children) - 1)):
            failures.append('AppleARMCPU 匹配项仍会与 ArmCpu 争用 CPU 节点')
            break
    for name, value in sorted(found.items()):
        segment = next((s for s in segments if s[0] <= value < s[1]), None)
        if segment is None:
            failures.append(f'{name} = {value:#x}：不在任何映射段')
        elif name not in REQUIRED and not segment[2] & 4:
            failures.append(f'{name} = {value:#x}：不在可执行段')
    return found, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    try:
        bindings, failures = inspect(args.kernel.read_bytes())
    except (ValueError, OSError, struct.error) as exc:
        parser.exit(2, f'检查失败：{exc}\n')
    for failure in failures:
        print(failure)
    if failures:
        parser.exit(1, f'{len(failures)} 项内核地址检查失败；不要把镜像作为启动候选。\n')
    print(f'{len(bindings)} 个存储绑定位于映射段，预链接信息位于组件之后；仍需核对运行时行为。')


if __name__ == '__main__':
    main()
