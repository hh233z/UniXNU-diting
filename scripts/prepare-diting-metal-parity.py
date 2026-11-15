#!/usr/bin/env python3
"""Prepare a separate pinned translator tree for Diting's iPadOS18 Metal bridge.

The input is the public steelbrain/metal2vulkan Git repository. Existing dirty
translator worktrees are never reset. Applies the feature branch's ordered
patches and the matching guest format ABI adapter; no firmware or images.
"""
import argparse,io,json,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from diting_metal_sources import PIN, PATCH_DIRECTORY, validate_parity_sources
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--repository',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():p.error('output already exists; preserve it or choose a new path')
source=subprocess.check_output(['git','archive',PIN],cwd=a.repository)
a.out.mkdir(parents=True)
with tarfile.open(fileobj=io.BytesIO(source)) as archive:
    archive.extractall(a.out,filter='data')
patches=sorted(PATCH_DIRECTORY.glob('*.patch'))
for patch in patches:
    subprocess.run(['git','apply','--whitespace=nowarn',str(patch)],cwd=a.out,check=True)
(a.out/'.diting-parity.json').write_text(json.dumps(dict(translator=PIN,guest='22H374',
    metal='b82fa2751d62d3b0a8b9330a58d1506d9cdf0963',patches=[p.name for p in patches]),indent=2)+'\n')
validate_parity_sources(a.out, '22H374')
print(a.out)
