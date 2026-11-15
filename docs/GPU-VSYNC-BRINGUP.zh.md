# A730 与显示同步接入记录（2026-11-15）

## 同 SoC 参考

- cotunjr/hakios-mayfly，de73cdbe5dba410ed198456c6737bf383f900eaa；公共内核 mayfly-port，9d3c291a9f9f4082d9571f9b2984d0026778a36b。Xiaomi 12S / SM8475 / A730，iOS 16.5。README、FINDINGS 和 gpu645 日志记录 GMU、HFI、SMMU、ZAP、CP 分阶段初始化；UI 走 freedreno OpenGL ES。用于核对硬件流程，不能直接替换 Darwin24 / Metal 用户态，也不能复制其 ZAP 保留地址或面板寄存器。
- qiumochen/UniXNU-zizhan，034a0b0037b28f4ff4e46703cbd4d9bb75db25e5。MIX Fold 2 / SM8475 / A730 / 22H374，Turnip + metal2vulkan，与当前软件栈更接近。README 报告 g298 合成滑动 moving 95.3 fps，首帧仍约 75–80 ms；这是对方特定测试，不能作为 Diting 实测或全局 120 fps 证据。

来源：https://github.com/cotunjr/hakios-mayfly 与 https://github.com/qiumochen/UniXNU-zizhan 。固定版本参考文件保存在开发机，未导入其他设备的固件或私有数据。

## 本轮具体修改

新增 diting_ipados18_bringup_gpu_defconfig：只在当前已工作的 power/touch/Data 配置上启用 DitingAdreno 平台，Wi-Fi 保持关闭。CI 提供独立选择。启动仍由 diting_adreno_start=1 控制；用户态库、Metal 插件发现、真实 CP fence 与完成帧是后续必需条件。配置启用不等于 GPU 加速已经可用。

现有 MiniIOMobileFramebuffer 的提交等待与 VSync 通知使用不同的相位，回调延迟后按当前时间重新定相。改为同一单调时钟周期网格；每个周期最多允许一个软件提交，同周期过早提交等下一拍，已经迟到的帧立即放行，不再额外补等；通知计数包含错过的周期，并报告最近边界而不是陈旧的计划时间。未完成 surface 在等待节拍前退出。

这仍是软件节拍，不是面板 TE / DPU 完成中断，不能宣称消除了撕裂。真实垂直同步需要确认 Diting 自身的扫描缓冲区、TE 路由和 DPU 原子翻页，不能照搬 mayfly 或 zizhan 的显示地址。当前保留已有扫描输出所有权。

## 验证状态

本地通过补丁格式/空白检查，60/90/120 Hz 的周期算法检查覆盖快速连续提交、迟到提交、周期对齐。先前软件扫描行优化完成 117 个实际 ARM64 callback 覆盖检查。均不代表实机帧率或画面无撕裂。两种配置的 GitHub 编译及本机验证尚待结果。


## 第 60 版实机证据

2026-11-15，Diting / 22H374，镜像来自 CI 43681577116，源码 28a744a。
用户确认桌面正常并返回 Android。原生 Data xid 9176 的
`/private/var/logs/DitingAdreno-kernel.txt` 保存了本轮 22 条启动记录的最后 10 条：

- GX OOB/START、GBIF release、CP_ME_INIT drain 均 result=0。
- PAS13 ZAP auth、CP nonsecure switch、CP fence 均 result=0。
- GPU IRQ332 owner、CP ready、CP/user-client startup 均 result=0。
- fence 观测值与期望均为 1；GPU timestamp 为非零 0x373468。

对应源码先提交 PM4 实际内存写入并核对 scratch 值，再注册 IRQ、读取 GPU timer，
最后发布 native user client。因此已取得底层 CP 执行和用户客户端发布的实机证据。
这不是 Metal 绘制、着色器编译或桌面 GPU 加速证据；本轮仍含
`diting_ui_software=1`，也未启用软件调度库安装。

后续应完成匹配 22H374 的 Turnip / Metal bridge / discovery bundle 构建与原生 Data
安装路径，验证真实 Metal device、绘制及完成帧后，再切换桌面渲染。
不能仅移除软件渲染参数就宣布 GPU 接入完成。
