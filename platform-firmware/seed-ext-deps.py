#!/usr/bin/env python3
"""Unpack the pinned Mu web dependencies so stuart update does not download them.

GitHub-hosted runners receive HTTP 504 for these two release assets. The
archives in platform-firmware/vendor are the upstream files; the sha256 values
are the ones in Mu_Basecore's ext_dep descriptors.
"""

import hashlib
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

EXPECTED = {
    "basetools-v2026080000.0.1.tar.gz":
        "a866e053855511985d1d73987024948c04add218530015b8e3c7af5b0996f6f4",
    "OneCrypto-Accelerated.zip":
        "c42f8d950b5546a062e3c652f3a23c4d12bbfa8a40d967a02367c5d614763661",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    vendor = Path(sys.argv[1])
    tree = Path(sys.argv[2])
    for name, digest in EXPECTED.items():
        path = vendor / name
        got = sha256(path)
        if got != digest:
            raise SystemExit(f"{name} sha256 {got} != {digest}")

    basetools = tree / "Mu_Basecore/BaseTools/Bin/Mu-Basetools_extdep"
    if basetools.exists():
        shutil.rmtree(basetools)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        with tarfile.open(vendor / "basetools-v2026080000.0.1.tar.gz", "r:*") as tar:
            tar.extractall(tmp)
        shutil.move(str(tmp / "basetools"), basetools)
    (basetools / "extdep_state.yaml").write_text("version: v2026080000.0.1\n")
    genfw = basetools / "Linux-x86" / "GenFw"
    if not genfw.is_file():
        raise SystemExit(f"missing {genfw}")

    onecrypto = tree / "Mu_Basecore/CryptoPkg/Binaries/onecrypto-bin_extdep"
    if onecrypto.exists():
        shutil.rmtree(onecrypto)
    onecrypto.mkdir(parents=True)
    with zipfile.ZipFile(vendor / "OneCrypto-Accelerated.zip") as archive:
        archive.extractall(onecrypto)
    (onecrypto / "extdep_state.yaml").write_text("version: 1.1.2\n")
    inf = onecrypto / "RELEASE/AARCH64/OneCryptoBin/OneCryptoBinDxe.inf"
    if not inf.is_file():
        raise SystemExit(f"missing {inf}")
    print("seeded Mu-Basetools and onecrypto-bin")


if __name__ == "__main__":
    main()
