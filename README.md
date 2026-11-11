# UniXNU-diting

Redmi K50 至尊版（`diting` / Qualcomm SM8475）的 UniXNU 格式 2 设备仓库。目标系统为
**iPadOS 18.7.10（22H374）/ Darwin 24.6.0**，系统输入为 iPad7,11 / J171AP。

- 核心构建工具：[UniXNU](https://github.com/UniXNU/UniXNU)
- 固件：本机 `uefi-diting` 开发树；`uefi-pong` 只作参考，其 FDF 内嵌的是 Nothing Phone (2) 的 DTB
- 官方说明：[仓库迁移](https://unixnu.com/zh/porting/migration)、[设备仓库](https://unixnu.com/zh/porting/device-repository)、
  [驱动适配](https://unixnu.com/zh/porting/drivers)、[启动验证顺序](https://unixnu.com/zh/porting/bring-up)、
  [日志抓取](https://unixnu.com/zh/porting/log-capture)
- 本设备：[格式 2 配置](migration/format2/README.zh.md)、[系统迁移](migration/ipados18/README.zh.md)、
  [结构化移植记录](porting.toml)、[AGENTS.md](AGENTS.md)

## 当前状态（2026-11-11）

- bring-up 第 6 阶段：UFS 三窗口（OS / SystemOS / Data）已发布，根卷按 UUID 匹配并挂载，
  `launchd` 已实机启动。
- 已验证的设备布局（userdata `0x2F8A00..0x3ADF3FA`，4 KiB LBA）：
  OS `0x100000`、SystemOS `0x198100000`、Data `0x285000000`，SHNGROOT v1 清单；
  三个卷 UUID 与内核内嵌的 `XNU_OWNER_*_VOLUME_UUID` 一致。
- 当前停点：准备用户态的 `launchd_cache_loader` 在 restore 模式下以
  `Failed to verify code directory` 退出。按 `migration/ipados18/services.md`（services9）的既有结论，
  启动参数需要 `launchd_unsecure_cache=1`；该参数已写入 `board.toml` 的 `kernel_args`。
- 日志不使用拍屏：固件每次启动读取 `0xA7000000` 的 ramoops 环（`RAMOOPS|`），下一轮启动用
  Advanced Logger 的二维码导出上一轮 XNU console。

## 组件与来源

`drivers/` 是社区 Pong SM8475 实现（A730 / QCA6490 / SM8475 UFS 等）的子模块，本设备复用其
板级代码。组件 ID 保持 `PongPlatform24` 以保留来源、ABI 与验证记录；不要把它标成上游
A740/WCN7850 实现。Diting 的板级配置在 `board.toml`、`dts/diting.dts` 和 `drivers/`。

## 构建

需要完整 Xcode（含 iPhoneOS SDK）、Python 3.12、dtc、匹配的 22H374 restore/ABI 输入和板级私有
固件。源版本由 `feeds.toml`、`unixnu.lock` 和迁移记录固定；克隆时加 `--recurse-submodules`。

CI 使用 `.github/workflows/package.yml`（仅 `workflow_dispatch`），在 macOS runner 上构建
kernel / payload / boot image，产物为 `diting-package` artifact。三个卷 UUID 是内核常量，换 userdata
必须重编内核；占位 UUID 的构建只能用于编译验证，不能上机。

## 源码边界

仓库只包含板级源码、补丁、配置和脚本。IPSW、Apple 私有二进制、固件、认证数据、userdata 和构建
产物不进入仓库，由脚本在本机获取或生成。设备级代码采用 BSD-2-Clause-Patent；导入组件保留原始
许可证及 SPDX 标记，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
