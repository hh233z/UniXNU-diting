# 22H374 软件扫描任务调度

## 动机与边界

第56版实机Data xid6696：2801帧的内核最终绘制均值1.578ms，表面等待近零；BackBoard栈命中软件image_sampler、scanline、dispatch_apply。没有完整逐帧用户态耗时，不能承诺本改动解决全部卡顿。

`fb_threads=8`只控制最终显示输出。本改动作用于22H374 QuartzCore的CPU扫描转换任务，保留采样、混合、裁剪、特效、输出分辨率与原生同步完成语义，不启用或假冒GPU。

## 已核对的算法

QuartzCore UUID `FAF7D7EA-18F0-3C2D-816C-AC56D16C40A3`。`draw_polygon`中`0x18453c95c`起40字节准备dispatch_apply计数与共享block。原实现高度大于7时安排`height/4`次回调，否则1次；共享行领取长度为4。

对应回调`0x18453c9d8`不使用dispatch迭代索引分配固定行。它通过block+0x50原子游标领取区间，block+0x44是领取长度，block+0x4c是截止行；成功领取后循环至末行。每个回调会从多边形起点准备状态，行已被其它回调领取完毕时仍有准备开销。

将大于7行时的回调数限制为8，将领取长度改为16，减少多余回调和共享游标竞争；不足16行的尾部由原生min(end,cursor+claim)处理。小图元从原来的2到7个回调可能变成8个，是否值得进一步设置自适应阈值应由实机结果决定，不先声称全面加速。

只在系统UUID、可执行段范围、整段原指令、页边界均匹配时修改backboardd的私有代码页。原调用仍是同步dispatch_apply，不绕开fence或提前返回完成。

## 交付与回退

macOS CI编译并以4KiB签名页签名项目自有`userland/sw_render18.c`。`build-diting-sw-render.py`生成不入库的内核include和独立运行时产物；用户态与内核同批构建。

仅`diting_sw_render=1`启用安装。内核在已有UUID/设备绑定检查通过、Data可写挂载和目录骨架建立后，使用原生vnode接口写入`/private/var/db/diting-sw18-v1.dylib`。检查父目录及文件类型、属主、写权限、所属挂载和文件链接数；不跟随符号链接；显式截断并同步完成后才允许注入。失败仅记录SKIP，原有UI适配库与启动流程继续。

只对backboardd追加新库，保留原库的触摸和其它适配。关闭参数或启动旧镜像就不加载；不覆盖OS/SystemOS或原`/diting/libditing-ui18.dylib`。当前路径在启动PID 1前写入，避免覆盖已被加载的库。未来内容/ABI变更应更换版本路径。

运行时写入`/private/var/mobile/Library/Logs/DitingSoftwareRender.txt`，记录APPLIED或SKIP及错误；APPLIED只证明指令安装成功，不代表性能提升。

## 本地检查与待实机项目

在本地匹配共享缓存上，以ARM64指令模拟执行原扫描回调，对4行和16行领取做117组矩形/三角形、1到2712行及边界尾部覆盖比较，扫描行范围一致且没有重复行。这不是速度基准，未模拟多核交错，也未覆盖全部像素着色器。

构建完成后需验证新库实际安装、APPLIED日志、触摸/画面无回归，并用连续操作窗口对照提交频率与负载；未经过这些步骤不能声称更流畅或达到60/120FPS。

同时对诊断日志使用显式vnode_setsize，修复第56版观察到的旧启动记录残留。分析器仍保留按累计计数回退分段的兼容逻辑。

2026-11-15 第57版：用户报告改善有限；实机Data xid7925的22个窗口均为sw_runtime_install_status=22，/db/diting-sw18-v1.dylib及用户态APPLIED日志缺失，故扫描行优化未生效。不能据此断定调度算法无效。下一版安装器使用与已工作的诊断文件写入相同的vfs_context_kernel，截断属性补IO_SYNC，并记录lookup/getattr/open/truncate/write/fsync/ready八阶段。EINVAL准确发生点仍待下一轮日志，禁止先声称已修复。
