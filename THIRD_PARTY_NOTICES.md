# Third-party source and asset notices

This repository is an unofficial, independent hardware port. It is not affiliated with, endorsed by, or sponsored by Apple Inc., Xiaomi Inc., Qualcomm Incorporated, or any other vendor. Trademarks belong to their respective owners.

## Source components

- UniXNU core, DarwinBoot, XnuPrelink, NativeUfs, NativeRamBlock, and the Adreno modules: retain their per-file SPDX identifiers and upstream repository licenses.
- `DitingPlatform24` and the vendored SM8475 device drivers under `drivers/` (originally derived from the community Pong SM8475 work): original sources and licenses are retained per file; the sources are renamed to Diting and the provenance is recorded in `AGENTS.md`. They are not upstream A740/WCN7850 implementations.
- uefi-diting / the Diting firmware package: derived from EDK2, Project Mu, and Silicium-ACPI; those licenses apply. The EDK II build tree is not vendored here; `platform-firmware/ditingPkg` carries the device package.
- Linux GPL-2.0 components: the ath11k/MHI/QMI bodies compiled from the pinned Linux source tree are GPL-2.0. metal2vulkan, Mesa, and Turnip components carry their own GPL/LGPL/MIT licenses.
- Project Mu, EDK2, and other build-time dependencies keep their upstream licenses.

## Apple restore assets

- The target restore is iPadOS 18.7.10 (22H374) for `iPad7,11` (J171AP). The OS, SystemOS, AppOS, trust caches, and related components are obtained from Apple's public restore service by local scripts at build time. No Apple restore binaries, caches, or IPSW contents are stored in this repository, its git history, or its public CI artifacts.

## Vendor / device firmware

- The board firmware blobs listed in `proprietary-files.txt` (Qualcomm ADSP/modem/QCA6490 `amss`, `amss20`, `m3`, `regdb`; Adreno 730 GMU/ZAP/SQE; NXP TFA9873 `tfa98xx.cnt`; Goodix touch firmware; Xiaomi device firmware) are the property of their respective vendors. They are extracted by the user from their own device or local firmware, are not stored or redistributed by this repository, and must not be committed or attached to public artifacts.
- Qualcomm, NXP, Goodix, and Xiaomi firmware is used only on the user's own hardware under the vendors' terms.

## No warranty

The device-level LICENSE does not replace a component's file-level license. This repository is provided as-is for research; see the README disclaimer.
