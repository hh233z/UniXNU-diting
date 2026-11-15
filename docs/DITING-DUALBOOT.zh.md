# Diting 双系统菜单

2026-11-15：第一阶段为临时 RAM 启动菜单，尚不是可永久安装的双启动 boot。

## 当前实现

在现有已启动过 Diting iPadOS 18.7.10 的 UniXNU 图形菜单上适配目标选择：Android 为默认项，10 秒无操作冷重启，回到未改动的 Android 活动槽；音量键选择、电源键确认，首次按键取消倒计时；iPadOS 沿用原有 XNU entry 的全部字段；保留 Tools 日志入口。使用固件提供的 GOP 和按键接口，不依赖另一个设备的面板、字体或物理地址。菜单触控尚未接入。

参考 Mi8 Dual-Boot Lab 的分层方式、默认 Android 和输入取消倒计时交互，未复制其 SimpleInit/LVGL 源码或图形素材。当前 UI 实现仍来自 UniXNU，相关 BSD-2-Clause-Patent 归属保持不变。Mi8 的专用地址标记、BootShim、充电识别、关机寄存器和分区布局不适用于 Diting。

- 参考仓库：<https://github.com/Hercules-Zhaoziyi/mi8-dualboot-lab/tree/18f673ed63ded7ea0c42c8f70faab26f3261f4e3>
- 当前固件参考：Emilelu/uefi-mondrian e06211de59325bbd086c312324bdbf40e21d1045，UniXNULib 的 Menu.c、Config.c、Boot.c。Reset action 调用 EFI ResetSystem(EfiResetCold)，未写 Mi8 的交接标记。

## 生成

安装 pyfatfs，使用 Python 3.11 或更新版本：

```sh
python scripts/prepare-diting-dualboot.py --source <已有Diting候选.img> --output <新的RAM测试.img>
python scripts/test-diting-dualboot.py
```

生成器要求 Android boot v3/v4、完整 PONGFAT1 边界和唯一的 Diting 22H374 XNU 项。保留其他 payload、内核参数、系统镜像与 ADT，只修改菜单和格式要求的 FAT CRC。拒绝覆盖输入或已存在的输出。JSON 记录明确标注未验证与禁止永久安装；脚本不运行 adb/fastboot，不写设备。

## 验证与后续

本地菜单测试覆盖默认入口、XNU 字段保留、重复生成、错误设备、多个 XNU 入口、超界倒计时。主机测试不能证明按键或冷重启在实机有效，实机结果须单独记录。

**只能 fastboot boot 临时运行，不能 flash 到 boot。** 此阶段 Android 入口依赖原厂活动 boot 保留；永久装入该菜单后，冷重启会再次进入菜单，不能当成完成的 Android 交接。永久开机选择还需要实现并验证 Diting 的 Android 载荷交接、镜像容量/槽位兼容以及独立回退路径。不能以切换未验证的 B 槽替代这项工作。

2026-11-15 首轮设备记录：以既有第56版为基础生成10秒菜单候选，fastboot boot 的发送与启动均成功；随后 ADB 重新连接到 Android，活动槽仍为 A。菜单画面及倒计时触发原因待用户确认，不将 ADB 重连单独视作两个入口均已通过。未执行 flash、切槽或系统分区写入。

2026-11-15 第二轮设备记录：60秒菜单候选临时启动成功，用户明确确认“菜单按键正常，已进入 iPadOS”。据此仅将菜单可见、按键选择及 iPadOS 入口标为实机通过；首轮用户未留意屏幕，Android 自动倒计时仍只有重连证据，菜单触控及永久安装均未验证。

永久交接调查：2026-11-10 Android备份的 boot_a 是 v4，内核含 ARM64 Image 与 MZ 标志，具备进一步核对 EFI stub 的价值；boot/vendor_boot 均为v4。仅凭标志不能证明可由本 UEFI 正确链式启动，仍需当前设备 boot/vendor_boot、FDT、bootconfig、AVB及内存保留关系核对。旧备份不直接用于当前Android交接。

2026-11-15 Android交接阶段：已只读取得当前A槽boot/vendor_boot、DTBO、运行中FDT/cmdline/bootconfig。新增prepare-diting-android-payload.py，校验v4头、AArch64 PE入口及单个正常vendor ramdisk，拼接vendor+generic ramdisk与Linux bootconfig尾部。私有载荷仅留开发机。独立RAM候选复用现有UniXNU Linux EFI加载器，当前Android FDT与LoadFile2 initrd，增加efi=novamap参数；保留冷重启返回项。fastboot临时发送/启动成功，实际Linux接管与Android桌面结果待用户确认，未写永久boot。候选暂不包含iPadOS载荷，目的是单独确认Android交接。

Android EFI v1实机失败：用户报告卡住。照片确认EFI stub已启动、选用配置表DTB、通过LINUX_EFI_INITRD_MEDIA_GUID加载initrd，最后输出Exiting boot services and installing virtual address map。由此排除“菜单未调用内核”和“LoadFile2未加载initrd”；仍无法区分ExitBootServices、虚拟地址映射或Linux接管后的停顿。屏幕保留菜单是旧帧，不能据此认定仍运行菜单；待回Android后读取pstore。永久安装继续禁止。

Android EFI v2：增加efi=noruntime、earlycon=efifb、keep_bootcon、ignore_loglevel、loglevel=8。用户见新内核文字，约5分钟后自动进入Android；随后ADB采集显示efi: UEFI not found且上述测试参数全部缺失，确认当前为原厂引导Android，不能将本轮记为EFI直接交接成功。pstore为空，具体复位原因不明；需捕获新内核文字定位，永久安装尚不具备条件。

照片补充更正：v2确已越过EFI并启动八核、UFS、/init、挂载system/vendor及执行第二阶段厂商模块加载；此前将停顿限定EFI附近的推测不成立。正常原厂日志在0.287秒执行/init、1.045秒第二阶段；照片约14秒执行/init，58秒仍在模块加载。全量earlycon/ignore_loglevel可能显著增加同步屏幕输出开销，但尚无自动重启根因证据。新增本机v3低输出对照，移除earlycon/keep_bootcon/ignore_loglevel，统一loglevel=3，保留efi=novamap及efi=noruntime；kernel/initrd/FDT不变，等待实机测试。

v3低输出测试：用户报告进入Android桌面，但随后ADB确认efi: UEFI not found，cmdline仍原厂loglevel=6，无efi=noruntime/novamap/loglevel=3；故本轮仍未证明EFI直接启动Android。不能因看见桌面就发布常驻菜单。已保存当前dmesg/logcat/properties，继续定位交接后重启。

v4持久日志取回：EFI v2.70/Project Silicium及probe-v4参数确认来自真正EFI测试。内核在约1.1秒进入init第二阶段，持续到111秒；失败链为低4GiB动态CMA耗尽 → qseecom_region/audio/display/WLAN分配失败 → qseecom probe -22、设备节点缺失 → keystore无法建立TEE、vold等待数据卷解密。正常原厂日志上述池全部分配成功。临时modules.rc已与原始备份一致。新增默认关闭的DITING_ANDROID_CMA_ENABLED，仅Android专用固件构建启用：D5C00000+A400000及F4600000+BA00000，共350MiB，均包含于本机captured /memory且不重叠固定reserved-memory节点。前者原厂动态显示CMA不是固定保留区。构建与实机修复效果待验证，不修改加密状态/密钥。
