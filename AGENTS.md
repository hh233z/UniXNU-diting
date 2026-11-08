# Pong probe policy

- Optional probes must record PASS, FAIL, SKIP or RUNNING and return to the normal boot path. Never terminate boot with panic, halt or an unbounded loop to display a probe result.
- On failed prerequisites, log the reason and skip dependent MMIO/DMA work. Do not fabricate successful services, media or hardware resources to keep boot moving.
- Save bounded result snapshots through PongProbeRecord. The early panic hook must print completed snapshots before the real panic message, without allocating, taking registry locks or accessing hardware.
- Preserve real kernel panic handling and functional invariants. A failed optional probe does not authorize suppressing a genuine fatal kernel error.
- Keep Pong DT/hardware constants specific to SM8475. Refer to Sheng for implementation structure and adapt its SM8550 values before use.
- Prefer temporary fastboot boot for device trials. The user has also authorized entering Android to read partitions and clearing userdata/other required partitions for this port. Use that authorization when a concrete installation step needs it; verify target geometry and keep required boot/firmware backups before destructive writes.
- After completing a build and installing any matching runtime update, temporary fastboot boot is the default authorized next step. A later explicit request to hold a particular image takes precedence. Leave the device running after boot for the user's observations.

# Local build preference

- The user explicitly requested skipping image hashes, image audits and device image readback verification. Use `--skip-image-verification` for kernel/boot builds and the default non-verifying Pong userland workflow. Do not run verification or benchmarks unless the user asks.
- Keep generated candidates and runtime artifacts under `/Volumes/PongDev/build/servicesNN`, logs/install receipts under `/Volumes/PongDev/logs/pong/servicesNN`, and temporary task scripts under `/Volumes/PongDev/tmp/servicesNN`. Never write these into the user's Downloads directory.
- The user requested deleting superseded temporary candidates and logs. Retain current deployment metadata and required compiler/firmware inputs; retire the previous candidate after the replacement is deployed. Keep original project sources and user scripts.
- For system updates, the user requests changed parts only. Refresh the unmounted guest OS with `scripts/sync-pong-os-for-update.py` before local edits, then use begin/stage/finish and install changed bands. Keep REC quiescent until the update is installed so guest filesystem changes are preserved. Do not blindly overlay old host APFS metadata after a guest boot.
- DarwinBoot24 and the selected XNU boot_args ABI have a 1024-byte command-line array, including the NUL terminator. Keep the assembled ASCII boot command at most 1023 bytes. Shorten optional log filters instead of changing the ABI or silently truncating functional boot arguments.

# Repository layout

- This is the Pong SM8475 format 2 device repository, targeting iPadOS 18.7.10 / 22H374 / Darwin24. Follow https://unixnu.com/zh/porting/migration and https://unixnu.com/zh/porting/device-repository.
- Keep the ARM64, SM8475, OS profile and board layers separate. The versioned SM8475 seed is under migration/format2/soc-seed; local overrides belong in ignored local.toml.
- Preserve community component identity PongPlatform24. Do not label the A730/QCA6490 implementation as the upstream A740/WCN7850 driver.
- Publish source/configuration/porting records only. Apple restore binaries, generated ABI dumps, firmware, userdata, credentials and build artifacts stay local.
- Record host build results separately from device results in porting.toml. A successful build or Fastboot command is not evidence of working Wi-Fi, PCM audio or buttons.
- Keep XNU_PONG_POWER independent of Wi-Fi. Shared RPMh/SMMU locks belong to PongPlatformResources, and Darwin24 links native4K helpers once through libPongSmmu4K.a.
- Native public prerequisites are pinned in configs/pong-native-sources.toml. Use scripts/fetch-pong-native-sources.py and ignored local.toml paths; do not reintroduce host volume paths into recipes.

# Diting packaging status (2026-11-06)

- Keep scripts/package.sh identical to the UniXNU template and use device driver submodules. The workflow pins the previously used UniXNU revision and installs the device OS profile and component catalog before packaging.
- The pinned upstream core receives a temporary generic kernel-component patch; board.toml selects PongPlatform24. The workflow uses the CI configuration, native-only kernel staging and the volume-layout artifact from the specified run. This integration has only local tests, not a successful macOS run. The layout must match the userdata image retained from that run. Do not treat the output as device-tested.
- Pong firmware is a reference, not validated Diting firmware. Record host builds and hardware results separately.
- The Pong firmware FDF separately embeds `Platforms/Nothing/pongPkg/FdtBlob/sm8475-nothing-pong.dtb`; it identifies Nothing Phone (2), regardless of the Diting DTB generated for the boot image. Do not claim that the firmware itself carries a Diting tree.
- Pong's firmware region at 0xA7100000–0xA7400000 overlaps the Diting ramoops reservation at 0xA7000000–0xA7400000. Pong firmware is not a Diting boot candidate, even if it compiles; derive and validate a Diting memory map before device testing.
- `uefi-mondrian-reference` is an independent Xiaomi SM8475 firmware reference, not a Diting port. Its documented UEFI menu result does not establish XNU boot; its DarwinBoot targets Darwin 22, while this project targets Darwin 24.
- The reconstructed Diting DTS retains incomplete board resources and an unverified RAM declaration. `dtc` success is not evidence that the original DTBO, UEFI tree, memory map or peripherals are correctly adapted.

# Diting Wi-Fi 构建进展（2026-11-07）

- Actions 运行 42350648631 的内层日志显示，所用 Sheng main 引入了与设备清单不同的 Ath12kWifi，31 个编译单元因此找不到 `linux/kconfig.h`；Linux 稀疏检出还缺少 MHI 和 QMI 源码。
- `scripts/prepare-ci-wifi.py` 根据 `configs/pong-native-sources.toml` 固定 Linux、Sheng 和 Ath12kWifi，检查 ath11k、MHI、QMI、shim 及头文件。工作流先独立编译 Wi-Fi，再进入较耗时的内核构建；检查日志会随失败产物上传。
- 使用清单中的 Linux 和 Ath12kWifi 固定版本，本机 Linux 交叉编译已生成 arm64 Mach-O 对象及 `libPongAth11k.a`。macOS/Xcode、内核最终链接、固件加载和 Diting 真机 Wi-Fi 仍需分别验证。
- 这是本地未提交修改；在 33 授权提交推送前，远端 Actions 不会使用这些改动。请勿把编译归档或占位卷布局当成设备功能证据。

# Diting 实机 panic 与构建检查（2026-11-08）

- 33 的照片显示 XNU 已进入 IOKit。greenA 内核 PC 0xfffffff00793ef74 对应 OSMetaClass::postModLoad，访问的 FAR 为 0xfffffff00da591e0，恰好等于 IOBlockStorageDevice::gMetaClass 符号 0xfffffff00da591d0 加 0x10；该地址不属于 greenA Mach-O 的任何映射段。
- 存储绑定由 prepare-ipados18-storage.py 根据 22H374 内核和固定 prelink 基址 0xfffffff00b000000 生成，board.toml 当前 slide 为 -0x1000000；greenA 实际 __PRELINK_TEXT 为 0xfffffff004130000。检查原始输入和 bindings 之前不要盲改 slide，也不要继续把 greenA 用于真机。
- 新增 scripts/check-storage-bindings.py，工作流在 v4 镜像组装前检查最终内核的 IOBlockStorageDevice 绝对符号是否落在映射段，方法地址另检查可执行权限。greenA 实测报 9 个不匹配，内存中模拟已映射符号的正向检查通过；这只是静态范围检查，不证明类结构、映射或启动成功。尚未提交或运行 CI。
- 另需修复 greenA 内核内 Pong ramoops 的 0x85200000 地址和 Diting 实机 0xa7000000 保留区不一致，并核对与固件区间的冲突及 pstore 格式。未经核实不要将保留区改成任意地址。
- 2026-11-08：根据 greenA 已映射段和旧配置反推的 22H374 起始地址，候选 slide 设为 0x5ed0000，使预链接基址对齐存储绑定的 0xfffffff00b000000；Diting 两份配置暂时关闭 Pong 固定物理地址的 ramoops；实际 payload 启用 -v，manifest 从 payload 配置读取相同参数。提交 43e14aa 已推送并启动 Actions 42404848268；CI、生成映射和真机启动均待验证。
- Action 42404848268 在内核链接失败：关闭 ramoops 后 kern_exit.o 仍引用 pong_ramoops_diagnostic_write。提交 92b3ef7 将诊断入口和调用按同一构建开关编译，并把宏传入 kern_exit.o；两种开关状态的预处理检查通过。新 Action 42407447526 已启动，尚未通过 CI 或上机。
- Action 42407447526（92b3ef7）成功：内核以 0x5ed0000 预链接，9 个存储绝对绑定落入映射段，实际 boot args 含 -v；Wi-Fi 仅通过预编译。尚未在 Diting 测试该镜像。后续提交 7fa0fb9 只处理 ramoops 开关切换后的增量对象失效，未被本轮 CI 覆盖。
- 33 要求刷入后，Action 42407447526 的镜像已写入 Diting 的 boot_b（Fastboot 写入 OKAY）；当前活动槽仍为 a。随后同一镜像经 fastboot boot 临时启动，命令返回 OKAY；OS 实际状态未确认，暂未发现 ADB 或串口。未通过 Fastboot 写入 boot_a 或 userdata。
- 33 随后提供的实机画面显示 corecrypto/pthread 的入口范围校验失败，接着 `IOPlatformExpertDevice::generatePlatformUUID` 调用 `sha1_init`，空指针访问 0x28 导致 panic。对 CI 42407447526 内核分析发现组件 Mach-O 的入口落在组件代码段，但父内核的 `__PRELINK_INFO` 结束地址低于这些组件；Darwin 24 将其用作静态地址上界，`ml_static_slide` 可能将高地址段清零，解释范围校验失败，需用下一轮实机验证。不要通过跳过 OSKext 检查掩盖。
- 手机重启回 Android 后，ADB root 直接检查 `/sys/fs/pstore`，目录为空；Android 实际 ramoops 参数为基址 0xa7000000、总长 0x400000、console 与 pmsg 各 0x200000、ECC 和 record_size 均为 0。该轮 XNU 因先前禁用写入器不能回读其日志。当前修改正使用设备配置为 Diting 传递该基址，并修复预链接信息位置；构建和设备日志回读尚待验证。
- Action 42411722700（6d1299b）通过并已临时启动，33 报告出现内核文字或 panic；随后 Android pstore 为空。内核反汇编确认日志地址 0xa7000000。向 Android `/dev/pmsg0` 写入短标记并正常重启后，pstore 仍为空；Android dropbox 未找到记录，原因未确认，不能把持久日志回读标为成功。该轮没有覆盖 boot_b。
- 33 明确允许清空 userdata 安装；但必须等匹配的 22H374 OS、SystemOS、Data 完整就绪、恢复写入环境可用、Diting UFS 和实际几何经过核对后才执行，不能提前擦除。当前 Android `/data` 为 F2FS，实测 userdata 4K 首 LBA 0x2f8a00、末 LBA 0x3adf3fa。
- CPU 诊断镜像越过 AppleARMCPU，现停在 Failed to mount root device。其 ADT 缺少 ufshc；当前 Pong UFS 固定使用另一机型的 userdata 几何，且设备尚未安装 SHNGROOT/APFS。Diting UFS 几何适配在独立 fork 准备中，OS、SystemOS、Data 不在当前 CI 成品中。
- 557e4f8 的 CPU 匹配修正在 Action 42416561746 通过；同等本地诊断镜像已真机越过 AppleARMCPU，停在根设备挂载。Diting UFS 分区范围适配已在独立仓库 nagatoquin33/diting-ufs 提交 4fe0173（unixnu topic），主仓库 c67bc72 接入该子模块、发布 UFS 节点和实测边界；安装准备期间保留只读。Action 42419087356 验证中，尚未声明 UFS 实机工作。

# Diting bring-up state (2026-11-08)

## Target
- Device: Redmi K50 Ultra `diting`, SM8475 (Cape family), Android 16, bootloader **unlocked**
  (`fastboot getvar unlocked` = yes; the `ro.boot.flash.locked=1` property is spoofed), active slot `_a`.
- Target OS: iPadOS 18.7.10 / 22H374 / Darwin 24, built as `DEVELOPMENT_ARM64_PONG` (MACHINE_CONFIGS=PONG).

## What is proven
- CI `package` runs green end to end: kernel links (`mach.development.pong` ~17.8 MB), payload, three containers.
- Diting's own UEFI (`ditingPkg`, RELEASE, 3,145,728 B `SILICIUM_UEFI.fd`) builds in a Linux job and is packed
  into `boot/pong-unixnu-uefi.img` (kernel slot = gzip(112 B BootShim + FD) + DTB, ramdisk = PONGFAT1 envelope).
- On hardware, `fastboot boot` of that image reaches the UniXNU menu, renders at 1220x2712, finds block IO
  (`blockio=1 volumes=1`) and DarwinBoot returns `HANDOFF EXIT RETURN 0`. The kernel then dies silently.

## Open blockers
1. Kernel death after handoff: no screen output even with `-v debug=0x144`, `/sys/fs/pstore` is empty.
   Next: firmware log via `Tools -> Advanced Logger` (QR, OneSend) and/or a real UART.
2. Wi-Fi: sources compile locally (`libPongAth11k.a`, 2,981 symbols) but CI stops in
   `build-pong-wifi-native.py` because the build reads `device-tree/build/pong/hardware.dtb`, not
   `PONG_HARDWARE_DTB`. The live tree (`/sys/firmware/fdt`) plus `platform-firmware/dtb-fixups/apply.py`
   provides PCIe/PHY/GPIO; the refgen clock is at `freq[10]` with `clock_names[8]` = `pcie_phy_refgen_clk`.
3. Wi-Fi firmware is checked in under `platform-firmware/wifi/` (amss.bin 5,470,128, amss20.bin 5,296,128,
   m3.bin 266,684, regdb.bin 24,278), pulled from `/vendor/firmware_mnt/image/qca6490` on the device.

## CI notes
- `.github/workflows/package.yml` has two jobs: `firmware` (ubuntu, builds the Diting FD and uploads
  SILICIUM_UEFI.fd + BootShim.bin + mkbootimg.py + diting.toml) and `package` (macos-15-intel, needs firmware).
- Before pushing, run `scripts/precheck-workflow.py` (bash -n on every run block, duplicate env keys,
  and every `--flag` against the script it targets). Both mistakes that broke earlier runs would be caught.
- `PONG_HARDWARE_DTB` is only meaningful for the Wi-Fi step; the kernel still uses the device-tree component's
  `hardware.dtb`.

## Artifacts
- `D:\ai\diting\artifacts\ci-20261107-diting-firmware\pong-unixnu-uefi.img` (first hardware boot, sha ac5aa923).
- `D:\ai\diting\build-work\greenB\...\pong-unixnu-uefi.img` (Tools menu enabled, sha FB2867EE).

- Apple 22H374 的 OS、SystemOS、AppOS 已在 WSL 本地提取/解密并只读挂载，未上传。用户态 helper Action 42458543571 成功，输出在 `D:\ai\diting\build-work\runtime-42458543571`。用户态 APFS 写入仅通过小样文件、属主与权限的独立读取；完整卷及设备均未验证，尚无可刷入的 userdata 成品。

## 2026-11-08 17:2x — Advanced Logger / firmware CDN

- On hardware the menu works, `Tools` is present (payload entry), but `Tools -> Advanced Logger`
  shows `Advanced Logger: no log`.
- Cause: the plugin reads through `AdvancedLoggerAccessLibGetNextFormattedLine`, which does
  `LocateProtocol(gAdvancedLoggerProtocolGuid)`. That protocol is installed by the DXE_CORE
  instance of `AdvancedLoggerLib`, and Mu's stock `Mu_Basecore/MdeModulePkg/Core/Dxe/DxeMain.inf`
  never consumes `AdvancedLoggerLib`, so the buffer is never created.
- Fix in the firmware job: insert `AdvancedLoggerLib` into `[LibraryClasses]` of `DxeMain.inf`
  before `[Guids]`, idempotently, in place (a patch failed because CI checks out Mu_Basecore
  3c9c7b2e, not the workstation revision, and the patch file lost its CRLF).
- Current blocker: the firmware job cannot fetch its external dependencies. Both
  `basetools-v2026080000.0.1.tar.gz` and `OneCrypto-Accelerated.zip` return **HTTP 504** from the
  GitHub release CDN, also from this workstation with curl, so it is an upstream outage, not our
  configuration. Retries (3x) and longer backoff do not help; the build resumes when GitHub serves
  the assets again.

