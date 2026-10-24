# AD9106 芯片有限次数 SRAM 播放（当前版本：每触发两遍）

本版本按用户要求删除 FPGA 自动停止 RUN、截止计时器、0x7FFE 配置地址以及 20 ms 等待。当前为排查约 25 ms 波形串，每次触发改为由芯片连续播放两遍 SRAM 单元后结束。此前自动停机方案和对应验证记录均不再适用于当前版本。

两遍版本验证：18 项 Python 测试、模块及完整顶层 XSim 均通过。以当前保存的 200 µs 静态单元测试，496 帧 UART 对应 3348 笔 SPI 写入全部匹配，0x2A/0x2B 均为 0x0101；每次触发后观察 30 ms 无自动写入或额外触发。[顶层仿真记录](firing_verification/chip_two/firing_uart.log)。本次仿真验证数字配置及接口，不模拟 AD9106 内部模拟输出。

两遍版 bitstream：`AD9106_demo.runs/impl_1/AD9106_two_patterns_20261023_231346.bit`，2026-10-23 23:13:46 生成，综合及实现完成、已有时序约束满足。SHA256：`F0528D6DC04012F1FE3810CA10E8CCDA7ED4069A42AEACCA5BCFABAFFD412393`。尚未烧录到板卡。重启上位机服务并刷新页面后，设置触发组数 1、重新发送配置，预期一次触发连续播放两个单元；仅刷新浏览器不能替换已运行的 Python 后端。

依据 [AD9106 Rev.C 手册](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9106.pdf)：第 24–26 页 pattern/trigger 说明及图 40–43、第 28 页 SRAM 访问、第 31 页 SRAM 启动步骤，以及第 42、45–46、52–54 页寄存器定义。RUN=1 后必须执行 RAMUPDATE，随后触发；[ADI 官方答复](https://ez.analog.com/data_converters/dds/f/q-a/110967/ad9106-when-to-set-ramupdate-and-run-bits)确认此顺序。

| 阶段 | 操作 |
| --- | --- |
| 配置准备 | TRIGGER 高；RUN=0。此处清零仅为重新配置/访问 SRAM，不能删除 |
| SRAM 写入 | PAT_STATUS=4（MEM_ACCESS=1、RUN=0）；写入左对齐的 12 位样本；写完 PAT_STATUS=0 |
| 波形参数 | WAVE_SEL=0 的通道读取 SRAM；配置 START/STOP_ADDR、HOLD、PAT_PERIOD；PAT_TYPE=1，0x2A/0x2B=0x0101，各通道字段 1 表示两遍 |
| 首次启动 | RUN=1 → RAMUPDATE=1 → 等待 1 µs → TRIGGER 下降 |
| 单元结束 | FPGA 不再写任何寄存器；RUN 保持 1、TRIGGER 保持低；芯片有限次数控制器结束输出 |
| 再次启动 | PC 发送 44；FPGA 拉高 TRIGGER，写 RUN=1、RAMUPDATE=1，等待后拉低 TRIGGER；不改 SRAM |
| 用户停止 | TRIGGER 高；数字增益、偏移、常数清零并 RAMUPDATE；不清 RUN、不产生新触发 |

当前静态扫描例：DAC3 SRAM 起点 0、终点 2969，共 2970 点；HOLD=5；PAT_PERIOD=14850、PAT_PERIOD_BASE=1，DAC 时钟 148.5 MHz，因此一个单元为 100 µs。样本中只有 10–20 µs 的一个正脉冲。DAC4 为恒压 Vgate，间隔时可能仍保持该电压。PC 控制单元之间的间隔及发送次数。

一次完整单元是共享 SRAM 公共时窗。各路频率不同时，一路在公共时窗中可包含多个模板周期；静态扫描限制为相同时窗，每个单元只有一个 Vin 脉冲。当前每次触发重复两遍，因此 100 µs 单元预期形成两个 Vin 脉冲、占用约 200 µs 播放时窗。界面“触发组数”为 PC 触发次数，组间等待时间从两遍播放结束后计算；设置组数 1 即测试一次硬件触发。

模块/顶层仿真检查 SPI 地址、数据和时序；触发后观察 30 ms，要求没有自动 SPI 写入或额外下降沿。回读应保持 0x1F=1、0x2A/0x2B=0x0101；播放后不再要求 RUN=0。回读是影子配置，仿真不等同于芯片模拟输出，25 ms 重复是否消除仍需实测。

此前单遍版本验证记录：模块及完整 BD 顶层 XSim 均通过，静态场景 449 帧 / 3018 笔 SPI 写入全部匹配；触发后分别观察 30 ms 无自动写入。18 项 Python 回归通过。由顶层实际捕获的 SPI 数据重建的 SRAM 单元见 [波形图](firing_verification/chip_single/four_channel_spi_reconstruction.png)，该图不是模拟电路仿真。单遍版 bitstream 于 2026-10-23 22:46:03 生成，保存为 AD9106_demo.runs/impl_1/AD9106_chip_single_20261023_224603.bit；它不包含本次两遍配置。
