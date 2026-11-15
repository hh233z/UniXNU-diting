#!/usr/bin/env python3
"""Pair an optional, fresh-only native APFS installer with the kernel.

No binaries or credentials are stored in the source tree. Without an explicit
runtime input the generated header contains no executable or injection path.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import zlib

ROOT=Path(__file__).resolve().parents[1]
NAMES=('DitingAdrenoMetal','DitingMetalBridge.dylib','libvulkan_freedreno.dylib','Info.plist')

def prepare(runtime,out):
    report=json.loads((runtime/'build-report.json').read_text())
    if report.get('guest')!='22H374' or report.get('chip_id')!='0x07030002' or \
        report.get('bridge',{}).get('device_extent')!=600:
        raise ValueError('installer requires the 22H374 / A730 / 600-byte bridge bundle')
    bundle=runtime/'DitingAdrenoMetal.bundle'
    if bundle.is_symlink():raise ValueError('bundle aliases are not installer inputs')
    if set(p.name for p in bundle.iterdir())!=set(NAMES):raise ValueError('unexpected bundle entries')
    info=plistlib.loads((bundle/'Info.plist').read_bytes())
    if info.get('CFBundleIdentifier')!='dev.unixnu.diting.Metal' or \
        info.get('CFBundleExecutable')!='DitingAdrenoMetal':raise ValueError('unexpected bundle identity')
    raw=bytearray();entries=[]
    for name in NAMES:
        path=bundle/name
        if path.is_symlink() or not path.is_file():raise ValueError('ordinary bundle files required')
        data=path.read_bytes()
        if not data or len(data)>64*1024*1024:raise ValueError('bundle file size out of bounds')
        if name!='Info.plist':
            if len(data)<32 or struct.unpack_from('<IiiI',data)!=(0xfeedfacf,0x100000c,0,6):
                raise ValueError('expected a thin arm64 dylib: '+name)
        entries.append(dict(name=name,offset=len(raw),bytes=len(data),mode=0o644 if name=='Info.plist' else 0o755))
        raw.extend(data)
    if len(raw)>96*1024*1024:raise ValueError('runtime exceeds the bounded installer working set')
    compressed=zlib.compress(raw,9)
    if len(compressed)>24*1024*1024:raise ValueError('compressed installer payload exceeds 24 MiB')
    payload=out/'gpu-install-payload.z';payload.write_bytes(compressed)
    header='#include <stddef.h>\n#include <sys/types.h>\n'
    header+='#define DITING_GPU_SOURCE '+json.dumps(os.environ.get('DITING_GPU_SOURCE','local-project-runtime'))+'\n'
    header+=f'#define DITING_GPU_RAW_BYTES {len(raw)}UL\n#define DITING_GPU_COMPRESSED_BYTES {len(compressed)}UL\n'
    header+='struct diting_gpu_file {const char *name;size_t offset,bytes;mode_t mode;};\n'
    header+='static const struct diting_gpu_file diting_gpu_files[]={\n'
    for e in entries:header+='{'+json.dumps(e['name'])+f",{e['offset']}UL,{e['bytes']}UL,0{e['mode']:o}"+'},\n'
    header+='};\n';(out/'gpu_install_payload.h').write_text(header)
    return payload,entries,len(raw),len(compressed)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--header',type=Path,required=True)
    p.add_argument('--runtime',type=Path,default=os.environ.get('DITING_GPU_RUNTIME_DIR') or None)
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    text='/* Generated project-owned installer; no default activation. */\n'
    if not a.runtime:
        text+='#define DITING_GPU_INSTALL_BUNDLED 0\n'
    else:
        payload,entries,raw,compressed=prepare(a.runtime.resolve(),out)
        if a.prepare_only:
            print(json.dumps(dict(entries=entries,raw_bytes=raw,compressed_bytes=compressed)))
            return
        sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
        common=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios18.0','-isysroot',sdk]
        # An assembler incbin avoids asking the C frontend to parse a 16 MiB byte array.
        assembly=out/'gpu-payload.s'
        assembly.write_text('.section __TEXT,__const\n.p2align 4\n.globl _diting_gpu_archive\n_diting_gpu_archive:\n.incbin '+json.dumps(str(payload))+'\n')
        obj=out/'gpu-payload.o';subprocess.run(common+['-c',str(assembly),'-o',str(obj)],check=True)
        installer=out/'diting-gpu-install-v1';launcher=out/'diting-gpu-launcher-v1.dylib'
        subprocess.run(common+['-Os','-Wall','-Wextra','-Werror','-I'+str(out),
            '-Wl,-no_fixup_chains',str(ROOT/'userland/gpu_install18.c'),str(obj),'-lz','-o',str(installer)],check=True)
        launcher_path='/private/var/db/diting-gpu-launcher-v1.dylib'
        subprocess.run(common+['-Os','-Wall','-Wextra','-Werror','-dynamiclib',
            '-Wl,-no_fixup_chains','-install_name',launcher_path,
            str(ROOT/'userland/gpu_install_launcher18.c'),'-o',str(launcher)],check=True)
        text+='#define DITING_GPU_INSTALL_BUNDLED 1\n'
        text+='static const char diting_gpu_launcher_path[]='+json.dumps(launcher_path)+';\n'
        for label,binary in [('installer',installer),('launcher',launcher)]:
            subprocess.run(['codesign','--force','--sign','-','--pagesize','4096',str(binary)],check=True)
            data=binary.read_bytes()
            if not 4096<=len(data)<=26*1024*1024:raise ValueError('bounded signed installer required')
            text+=f'static const unsigned char diting_gpu_{label}_blob[]={{\n'
            text+='\n'.join(','.join('0x%02x'%b for b in data[i:i+32])+',' for i in range(0,len(data),32))+'\n};\n'
        (out/'installer.json').write_text(json.dumps(dict(guest='22H374',chip_id='0x07030002',
            source=os.environ.get('DITING_GPU_SOURCE'),entries=entries,raw_bytes=raw,compressed_bytes=compressed,
            destination='/System/Library/Extensions/DitingAdrenoMetal.bundle',clients=['Preferences'],
            activation='diting_gpu_install=1 diting_rootful=1 diting_ui_software=1; next boot for GPU',
            device_tested=False),indent=2)+'\n')
    a.header.parent.mkdir(parents=True,exist_ok=True)
    if not a.header.exists() or a.header.read_text()!=text:a.header.write_text(text)
    print('Diting GPU install payload '+('built' if a.runtime else 'disabled'))

if __name__=='__main__':main()
