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
镜像50仅继承ST供电，后续修复按实测资源启用ldoc2及GPIO71；
前置条件不满足时记录失败并继续正常UI启动。

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

## 镜像 50 实测及后续修复

镜像50由CI43553231126成功构建并临时启动，用户确认锁屏可显示但触摸
完全没有反应。Data卷快照中，BackBoard在35秒时的输入线程停在
`input_thread` 的 `/dev/diting-touch` 打开重试，90秒时该线程已退出；
这支持输入设备未发布，尚不能判断是哪个初始化步骤失败。

该版本缺少ST供电初始化，只尝试继承电源状态。Android实机debugfs确认
GPIO71为2mA下拉输出高电平，`spi0.0-vdd`消费者连接`pm8350c_l2`，
电压1800mV；厂商`fts_enable_reg()`先启用总线电源，再拉高AVDD GPIO。
后续修复明确在ADT记录并校验这两项资源，通过命令数据库查找`ldoc2`，
完成真实RPMh投票后拉高GPIO71，再复位和探测ST。

仅当`diting_boot_snapshot=1`时，在30/90/180秒各尝试保存一个小型
`/private/var/logs/DitingTouch-kernel.txt`，记录实际初始化阶段、芯片ID、
电源资源地址及事件计数。文件失败仅记录错误，不阻断输入或UI。
供电遗漏已在源码确认，修复效果尚待实机验证。
