# Redmi K50 Ultra ST FTS L12 输入接入

2026-11-14，设备 `22081212C / diting` 的 Android 实机输入节点为
`/devices/platform/soc/990000.spi/spi_master/spi0/spi0.0/input/input7`，
名称为 `fts`，compatible 为 `xiaomi,l12-spi`。Goodix uinput 节点也存在，
但它不是这台设备当前使用的触屏坐标来源。

## 已确认的板级输入

| 项目 | Android 实测值 |
|---|---|
| SPI | QUP0 SE4，物理基址 `0x990000`，CS0，mode0，最大 12 MHz |
| 复位 / IRQ | TLMM GPIO20 / GPIO21 |
| 原始坐标 | X `0..12199`、Y `0..27119`，启用 super-resolution |
| I/O 供电 | `pm8350c_l2`，1.8 V |
| 固件 | 本机 `/vendor/firmware/st_fts_l12.ftb`，目标 ID `36:40` |

私有固件和设备日志留在本机，不进入此仓库。

协议依据为小米公开的
[fts_spi](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/bsp-diting-s-oss/drivers/input/touchscreen/fts_spi)：
`ftsHardware.h`、`ftsSoftware.h`、`ftsIO.c`、`ftsCore.c` 和 `fts.c`。
SPI 读硬件寄存器为 `0xFB` 加四字节地址及一个 dummy；
FIFO 读为 `0x87` 加一个 dummy，每条记录 8 字节。
L12 触点使用两个完整的 16 位小端坐标，不使用其它面板的 12 位格式。

## 本轮变更

现有 Darwin24 输入编译入口保留，增加按 ADT compatible 选择的 ST 分支，
不把 ST 包装成 Goodix。Goodix 路径保持独立；设备 ADT 明确选择 ST L12。
主机继续使用 `/dev/diting-touch` 及原有 down/move/up ABI。

ST 启动先读取真实芯片 ID，再复位并等待 controller-ready；
只有 Active Scan 命令收到匹配的 firmware echo 后才发布输入设备。
不上传或刷新控制器固件，不调用 Goodix 的 ldoc3/ldoc12 电源写入。
已上电的 ST 电源状态保留；前置条件不满足时记录失败并继续正常 UI 启动。

FIFO 是触点增量流，单条记录中没有出现的其它手指不应被释放。
只接受实际 finger/glove 的 down/move，leave 使用已记录的坐标释放。
复位、控制器错误或传输失败时释放已发布触点并停止输入线程；
不制造触点或假报硬件成功。

## 验证边界

Android 的硬件和协议来源已确认；修改后的 Darwin 内核仍需 macOS 编译和
本机临时 Fastboot 启动。GUI 照片只能证明 SpringBoard 已显示，不能证明输入修复。
49 保留为 GUI 回退镜像。首轮只验证 ST 输入，保留原有 CPU 数量和软件显示参数，
不同时引入 GPU、数据卷重建或充电策略修改。

下一轮设备结果应记录：芯片 ID、controller-ready、scan echo、
前几个真实触点，以及桌面点按/拖动/抬手表现。构建通过不等于触屏已可用。
