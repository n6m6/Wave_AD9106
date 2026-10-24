# 23 种模式的四路 Vin / Vgate 控制

已按指定 HTML 的图文实现输入激励模板。拓扑 3、5、6、7 各有 23 类，共 92 组、163 个主例/对照实验、326 个 Vin/Vgate 选择；加上同一序列的分段选择，共 504 种选择。任一路 DAC1～DAC4 均可分配 Vin 或 Vgate。完整编号及原文说明见 [FIRING_CATALOG.md](FIRING_CATALOG.md)，机器可读目录为 `waveforms/firing_catalog.json`。

这是图文重建的**输入激励**，不是神经元输出波形。HTML 没有原始 CSV、PWL/input.json；未明确给出的时刻、脉宽、斜坡形状用可编辑模板近似。原文标注未实现的神经元响应仍保留该判断，不能因生成了输入就认为该发放特性已实现。

## PC 使用

需要逐路选择、查看四路波形及扫描/切换串口时，可直接使用 [浏览器可视化控制台](FIRING_GUI.md)。以下命令行仍可独立使用。

在工程目录运行，Python 3.8 或以上。离线编译只需 Python 标准库；实际发送需要 `python -m pip install pyserial`。串口默认 115200、8N1，FPGA 控制时钟 100 MHz，SPI 1 MHz，DAC 采样时钟按原工程 148.5 MHz 计算。

先查询某组实验的 variant 编号；variant 从 0 开始，也可直接填写原实验标识：

```powershell
python tools/ad9106_firing.py catalog --topology 6 --mode 9
```

让 DAC4 输出拓扑 6、第 21 类的完整多幅值 Vin 序列，包络重复频率 100 kHz、最高幅值 5 V：

```powershell
python tools/ad9106_firing.py set --channel 4 --topology 6 --mode 21 --signal vin --component sequence --frequency 100000 --amplitude 5 --port COM3
```

只输出其中中档电压，其他已配置通道保留其波形配置：

```powershell
python tools/ad9106_firing.py set --channel 4 --topology 6 --mode 21 --signal vin --component mid --frequency 100000 --amplitude 5 --port COM3
```

以上幅值按完整原始范围缩放：原始三档 3/4.7/5 V，`--amplitude 5` 时选 mid 得到约 4.7 V；要单独提高该分量，可调整幅值、偏移或 JSON 中的 `parameters.levels_v`。`--amplitude` 不是峰峰值。

同时输出两对同步 Vin/Vgate（第一对 50 kHz，第二对 100 kHz）：

```powershell
python tools/ad9106_firing.py program --scene waveforms/example_two_pairs.json --port COM3
```

省略 `--port COM3` 只编译、检查并导出，不发送硬件。输出默认位于 `.uart_sim/firing_plan/`，包括 `plan.json`、四路 CSV、二进制指令及仿真输入。默认 `set` 保存各通道配置到 `.uart_sim/firing_scene.json`；使用 `--scene 路径` 可维护多套场景。`program` 读取已有场景。未列出的通道配置为零输出。

停止已启动的四路输出或清除一次中断的上传会话：`python tools/ad9106_firing.py abort --port COM3`。这会清零数字增益和偏移；名义零码电压仍取决于板级偏置。

四路共用周期和存储资源，所以每次改变一路，都会重新编译并上传完整场景，最后四路一起重启；其余通道的配置保留，相位会从新场景重新开始。连续两次 `set --port` 之间会有一次完整场景启动；配对输出请用一个 JSON、一次 `program` 下发。

## 23 类及分段分类

同图叠加的不同实验使用 **variant**；同一次输入中的多个电平、多个脉冲组使用 **component**。所有实验的 Vin/Vgate 电压范围和对照名称均列在完整目录中。

| mode | 模式 | 输入激励分类 / 可单独选择部分 |
| --- | --- | --- |
| 1 | 持续放电 | 正阶跃 Vin；Gate 工作平台 |
| 2 | 起始放电 | 正阶跃 Vin；不同幅值主例/对照用 variant |
| 3 | 持续簇发 | Vin 保持；Gate 多窗口 |
| 4 | 起始簇发 | Vin 保持；Gate 起始窗口 |
| 5 | 混合模式 | Vin 保持；Gate 斜坡/阶梯变化，按拓扑区分 |
| 6 | 频率适应 | Vin 保持；Gate 斜坡变化 |
| 7 | I 类兴奋性 | Vin 斜坡保持 |
| 8 | II 类兴奋性 | Vin 工作平台；近阈值幅值对照用 variant |
| 9 | 发放延迟 | 不同电压 Vin 探测脉冲分别列为 variant |
| 10 | 阈下振荡 | Vin 平台；Gate 正弦偏置或平坦对照 |
| 11 | 共振器 | Vin 脉冲列/单脉冲/重复列；Gate 正弦或窗口；对齐/错相等用 variant |
| 12 | 积分器 | Vin 近/远间隔脉冲组；`sequence/near/far/single`；拓扑 6 Gate 含向下缺口 |
| 13 | 反跳单发 | 负 Vin 后释放；保留原文正偏置对照 |
| 14 | 反跳簇发 | 负 Vin 后释放；对照用 variant |
| 15 | 阈值可变性 | Vin 探测序列配合多档 Gate；`sequence/low/mid/high` |
| 16 | 双稳态 | Vin 保持；Gate 停止阶跃 |
| 17 | 去极化后电位 | Vin 脉冲；幅值对照用 variant |
| 18 | 适应性 | 快/慢 Vin 上升沿用 variant；部分拓扑 Gate 有短窗口 |
| 19 | 抑制诱发放电 | 负 Vin 窗口 |
| 20 | 抑制诱发簇发 | 负 Vin 分组脉冲 |
| 21 | 全或无 | 多档 Vin 探测序列；`sequence/low/mid/high` |
| 22 | 不应期 | 双脉冲不同间隔及单脉冲对照用 variant；`pair/first/second` |
| 23 | 去极化阻滞 | Vin 斜坡保持；不同幅值实验用 variant |

未列出 component 的模式使用 `default`。`near/far` 保留该组内部时序；单选 `low/mid/high` 将所选电平的探测事件移到模板的首个探测位置。Gate 工作平台默认采用直流源，不反复播放实验启动时的一次性上电过程。拓扑 6 的默认 23 组预览见 [模板总览](firing_verification/topology6_template_overview.png)。

## 场景参数、频率与幅值

JSON 顶层包含 `dac_clock_hz`、`full_scale_v`、`zero_code_v`、`max_frequency_error_ppm` 和 `channels`。通道条目支持：

| 字段 | 含义 |
| --- | --- |
| `channel` | 1～4，通道不能重复 |
| `topology` / `mode` | 3/5/6/7；1～23 |
| `variant` / `component` | 实验变体及序列分段；默认 0 及目录中的首项 |
| `signal` | `vin` 或 `gate` |
| `frequency_hz` | **整段输入模板的包络重复频率**，必须为正数 |
| `amplitude_v` | 原始电压绝对峰值缩放到此值，再叠加 offset；默认原始峰值与 10 V 中较小值 |
| `offset_v` / `phase_deg` | 电压偏移 / 模板相位；默认 0 |
| `pair` | 同名两路须恰好一个 Vin、一个 Gate，模板、频率、相位和时序参数一致 |
| `enabled` | false 时该通道输出零码 |
| `parameters` | 修改下述参考模板参数 |

例如负 Vin 的 `amplitude_v:5` 表示最低约 −5 V；偏置会进一步平移整个波形。正弦 Gate 的载波频率在 `plan.json` 的 `sine_carrier_hz` 中单独报告，直流 Gate 的实际重复频率报告为 0。这里的频率不是神经元输出的发放频率，也不是脉冲列内部的脉冲重复频率。改变包络频率会等比例缩放脉宽、间隔和斜坡时长。

`parameters` 使用原图参考坐标的 us/V 单位，支持 `period_us/start_us/width_us/rise_us/fall_us/ramp_us/gap_us/pulse_period_us/pulse_count/gate_sine_period_us/gate_floor_v/gate_initial_v/gate_final_v/gate_baseline_v/levels_v`。各参数用于对应的波形族，例如 `levels_v` 是 15/21 类的三档电压，`gap_us` 用于第 22 类，`gate_sine_period_us` 用于正弦 Gate；不是每个模式都使用每个字段。第 22 类间隔从前一脉冲下降沿起点计量，包含下降时间。

后端按用户说明支持 ±10 V；本工程先采用名义换算 `V = zero_code_v + signed_code × full_scale_v / 2048`，默认 zero=0、full_scale=10。这是对板级传输关系的假设，需用实测校准，当前没有后端放大/偏置原理图。12 位码范围 −2048～2047，名义步进约 4.883 mV，正最大值约 +9.995 V。请求采样电压超出 ±10 V 会拒绝；原图 +12 V 激励默认整体缩放为峰值 10 V，计划中会提示。原文 3.5082/3.5085 V 等相差 0.3 mV 的对照，在固定 ±10 V 量程下可能得到相同数字码，不能保证保留该实验差异。

AD9106 的四路共用 4096×12 位 SRAM 及周期控制。实现采用公共超周期，把各路所需的整数个模板写入各自存储区；直流不占 SRAM，相同采样数组复用存储。HOLD/周期基数都在 1～16 中搜索；周期最长 65535 个周期基数单位。频率误差默认限制为 1000 ppm，并保证每个非直流包络至少 32 点、正弦载波至少 8 点。时序和寄存器约束依据 [ADI AD9106 Rev.C 手册](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9106.pdf) 的 SRAM、Pattern Generator 和寄存器章节。

因此各路可以有不同频率，但无法保证**任意四个频率组合**都能同时实现。存储不足、超周期过长或分辨率不够时，编译器在发串口前报错。`plan.json` 给出实际频率、码值、电压、时间步进和短平台量化数量；窄于一采样的平台可能量化为一点，不能认为仍保留原图脉宽。如需低频、多路任意独立频率且保留很窄脉冲，需要更换时钟/存储架构。

## FPGA 接口和事务流程

此次没有增加顶层端口，当前 BD 连线可继续使用：

```text
PC TX -> uart_rx_0 -> uart_cmd_rx.data/data_valid/frame_error
                         -> ad9106_cmd_parser.rx_data/rx_valid/rx_error
parser.cfg_valid/addr/wdata/last -> AD9106.cfg_valid/addr/wdata/last
AD9106.cfg_ready/cfg_done/init_done -> parser 同名输入
parser.rsp_valid/seq/cmd/status -> uart_cmd_tx 同名输入
uart_cmd_tx.rsp_ready/done -> parser.rsp_ready/rsp_done
uart_cmd_tx.uart_tx -> uart_tx_0 -> PC RX
```

三个串口模块和 AD9106 控制模块均使用同一 100 MHz 时钟和复位，AD9106 原 SPI/trigger/reset/clken 连线继续使用。PC 串口地与板端共地，使用与板端 IO 相符的串口电平。

新命令保持原 24 字节请求、8 字节回复格式；所有多字节字段为大端：

```text
请求：AA 55 SEQ CMD [18 字节 payload] XOR 0D
回复：55 AA SEQ CMD STATUS XOR 0D 0A
请求 XOR = 字节 2..21 异或；回复 XOR = SEQ ^ CMD ^ STATUS
```

| CMD | payload | 功能 |
| --- | --- | --- |
| `40` BEGIN | 全零 | 停止 pattern，将四路数字增益及偏移清零并 RAMUPDATE，进入上传状态 |
| `41` WRITE | 起始地址 2 字节、数量 1 字节、1～7 个 16 位数据、余下补零 | 连续地址的完整 SPI 写入；整块先检查，逐字等待完成 |
| `42` COMMIT | 全零 | 退出 MEM_ACCESS 后，配置单次播放、RUN=1、最后 RAMUPDATE=1，再公共触发四路 |
| `43` ABORT | 全零 | TRIGGER 拉高、四路增益/偏移/常数清零并更新，保留 RUN；维持静默，不恢复旧场景 |

`41` 可写地址为 parser 中 `scene_address_ok` 的允许列表，含波形配置及 0x6000～0x6FFF SRAM；禁止直接操作 RAMUPDATE、开启 RUN、复位或改 SPI 接口。SRAM 写入必须先写 PAT_STATUS=4，提交前必须写回 PAT_STATUS=0。上传期间 trigger 保持高，COMMIT 的最后一次更新后才拉低启动；ABORT 保持 trigger 为高。成功回复晚于 SPI 和规定更新等待完成。BEGIN 的更新同时清除原直流源增益和偏移，因为直流源不受 pattern 停止约束。

PC 使用停等协议，一帧回复后才发下一帧；序号按 8 位回绕。`STATUS=00` 成功，`02` 校验错误、`04` 参数/地址错误、`08` 场景状态冲突；其他状态沿用 [旧协议](UART_CONTROL.md)。收到成功回复说明 FPGA 已完成写入流程，**没有经 SDO 读回确认芯片实际接收**。发送失败会尝试 ABORT；串口断开无法保证该命令到达，恢复连接后可重新 BEGIN/上传，若此前会话未关闭须先 ABORT 或复位。

原 `01/02/03` 固定通道正弦/三角/100 kHz 步进方波仍在首次 BEGIN 前可用。首次 BEGIN 后 SRAM 布局已改变，旧指令返回 `08`，直到硬件复位；此时请统一使用新场景命令。复位仍播放原 demo 默认波形，场景不掉电保存。

## 仿真与综合

```powershell
python tools/test_firing.py
powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_firing_uart.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_firing_uart.ps1 -Top
python tools/analyze_firing_sim.py
& 'E:/Xilinx/Vivado/2023.2/bin/vivado.bat' -mode batch -source tools/check_top_project.tcl
```

顶层专项使用当前生成的 BD/wrapper、100 MHz/115200/1 MHz 正式参数，只有 MMCM 替换为功能时钟模型。模型仅用于隔离仿真，不加入 Vivado 综合源。新增测试可用 `source tools/add_uart_control.tcl` 加入 sim_1；脚本不修改设计顶层。修改 RTL 后正常重新综合、实现，不能复用旧 bitstream。完整结果及边界见 [FIRING_VERIFICATION.md](FIRING_VERIFICATION.md)。
## 单次播放与再次触发

当前采用芯片有限次 SRAM 播放，FPGA 不再执行截止计时或自动 RUN 清零。PAT_TYPE=1、四路重复计数=0；COMMIT 与再次触发 44 均仅写 RUN=1、RAMUPDATE=1，随后拉低 TRIGGER。PC 控制重复次数和完整波形之间的间隔；正常结束后 RUN 保持 1、TRIGGER 保持低。停止按钮拉高 TRIGGER 并将数字增益/偏移/常数归零，不清 RUN。详见 [当前流程](AD9106_SINGLE_PATTERN.md)。