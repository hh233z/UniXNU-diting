#!/usr/bin/env python3
"""Build a small project-owned runtime and embed it in the matching kernel.

The guest uses its native APFS driver after Data binding succeeds. No host
filesystem edits, Apple cache redistribution, or full OS image is needed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--header',type=Path,required=True)
    a=p.parse_args()
    source=Path(__file__).resolve().parents[1]/'userland/sw_render18.c'
    a.out.mkdir(parents=True,exist_ok=True)
    lib=a.out/'libditing-sw18.dylib'
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    runtime='/private/var/db/diting-sw18-v1.dylib'
    command=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios18.0',
             '-isysroot',sdk,'-O2','-dynamiclib','-Wall','-Wextra','-Werror',
             '-Wl,-no_fixup_chains','-install_name',runtime,str(source),'-o',str(lib)]
    subprocess.run(command,check=True)
    subprocess.run(['codesign','--force','--sign','-','--pagesize','4096',str(lib)],check=True)
    data=lib.read_bytes()
    if not 4096<=len(data)<=131072 or data[:4]!=b'\xcf\xfa\xed\xfe':
        raise RuntimeError('runtime must be a bounded thin arm64 Mach-O')
    text='/* Generated from project source; do not commit binary contents. */\n'
    text+='static const char diting_sw_runtime_path[]='+json.dumps(runtime)+';\n'
    text+='static const unsigned char diting_sw_runtime_blob[]={\n'
    text+='\n'.join(','.join('0x%02x'%b for b in data[i:i+24])+',' for i in range(0,len(data),24))
    text+='\n};\n'
    a.header.parent.mkdir(parents=True,exist_ok=True)
    # Preserve mtime when bytes are unchanged, so incremental builds remain valid.
    if not a.header.exists() or a.header.read_text()!=text:a.header.write_text(text)
    (a.out/'runtime.json').write_text(json.dumps(dict(runtime=runtime,bytes=len(data),
        boot_argument='diting_sw_render=1',build_complete=True,device_tested=False,
        source_revision=os.environ.get('GITHUB_SHA'),command=command),indent=2)+'\n')
    print(f'Diting SW18: built {len(data)} bytes; guest performance not yet measured')


if __name__=='__main__':main()
