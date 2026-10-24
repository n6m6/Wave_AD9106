# AD9106 串口控制与接口连接

本文描述 `01/02/03` 固定通道的原 demo 协议。新增的 23 类 Vin/Vgate、任意通道分配、四路同步场景及 `40/41/42/43` 命令见 [FIRING_CONTROL.md](FIRING_CONTROL.md)。首次进入场景模式后，旧命令返回状态 `08`，硬件复位后恢复。

已新增 `uart_cmd_rx.v`（串口输入）、`ad9106_cmd_parser.v`（指令解析及寄存器写入序列）、`uart_cmd_tx.v`（串口返回），均位于 `AD9106_demo.srcs/sources_1/new/`。
`AD9106.v` 增加了运行时写入握手端口，仍复用原来的 `ad9106_spi_writer`。没有修改顶层或 Block Design 连线。

## 1. 使用范围

| 指令 | 通道 | PC 指定的参数 |
| --- | --- | --- |
| `01` | DAC1 正弦波 | 开关、数字增益、数字偏移、24 位 DDS 调谐字、16 位相位 |
| `02` | DAC2 三角波 | 开关、数字增益、数字偏移、SAW_STEP |
| `03` | DAC3 方波 | 开关、数字增益、数字偏移、每帧周期数、占空比阈值、高低电平 |

DAC4 自定义波形不提供控制命令。为支持方波 100 kHz 步进，上电布局改为：DAC3 占用 SRAM `0x000..0x5CC`（1485 点），DAC4 占用 `0x5CD..0xB99`（1485 点）。DAC4 的原 297 点波形连续存放五次，保持原来的 500 kHz 波形周期。运行时命令不会改写 DAC4 的 SRAM、增益、偏移和地址配置。上电先执行 demo 初始化，之后才允许 PC 修改参数。

本版本对应当前 demo 的通道和存储布局，须保留 `SRAM_HOLD=1`、`PAT_PERIOD_BASE=1`、`PATTERN_PERIOD=1485` 及原有波形选择。RTL 默认值、BD 参数及 XCI 中的周期配置已同步到 1485；旧的生成文件需刷新模块引用并重新生成。若修改这些初始化参数，需要同步修改解析器的方波算法和 PC 频率换算。

**兼容性：**帧格式、命令号和模块接口保持不变，但方波 RATE 从“500 kHz 的倍数”改为“100 kHz 的倍数”，DUTY 的满量程从 297 改为 1485。旧方波命令需要重新组帧；例如保持 5 MHz，应将 RATE 从 10 改为 50，并重新计算 DUTY 和 XOR。

芯片的 RUN 和 TRIGGER 为全局控制。每条有效命令都会暂停四个通道并重新触发，DAC4 的连续输出也会短暂中断。默认先等待 20 ms，确保最长三角波周期结束后才继续写入；不保证通道之间的原有相位连续。

## 2. 串口参数与 PC 请求

默认 `100 MHz` FPGA 系统时钟、`115200 baud`、`8N1`、无流控，空闲电平为高。接收端有两级输入同步、起始位检查、停止位检查和 break 恢复。

每条请求固定 **24 字节**，使用二进制发送。多字节数值采用**高字节先发**；每个串口字节按 UART 的低位先发规则传输。

| 字节下标 | 内容 | 说明 |
| --- | --- | --- |
| 0..1 | `AA 55` | 帧头 |
| 2 | SEQ | PC 分配的序号 `0..255`，回包原样返回 |
| 3 | CMD | `01` 正弦、`02` 三角、`03` 方波 |
| 4 | ENABLE | `00` 关闭、`01` 开启 |
| 5..6 | GAIN | 12 位有符号增益编码，最高 4 位必须为 0 |
| 7..8 | OFFSET | 12 位有符号偏移编码，最高 4 位必须为 0 |
| 9..11 | RATE | 正弦：DDS 调谐字；三角：步长；方波：每 1485 点周期数（100 kHz 的倍数） |
| 12..13 | PHASE | 仅正弦使用，三角及方波填 0 |
| 14..15 | DUTY | 仅方波使用，正弦及三角填 0 |
| 16..17 | HIGH | 方波高电平，12 位补码；其他波形填 0 |
| 18..19 | LOW | 方波低电平，12 位补码；其他波形填 0 |
| 20..21 | `00 00` | 保留，必须填 0 |
| 22 | XOR | 字节 2..21 逐字节异或，不包含帧头和结束符 |
| 23 | `0D` | 结束符 |

GAIN 为 signed 12-bit / 1024：`0400` 表示 +1，`07FF` 接近 +2，`0C00` 表示 -1，`0800` 表示 -2。OFFSET/HIGH/LOW 的有符号代码范围为 `-2048..2047`，负值按 12 位补码发送，如 -1024 发 `0C 00`。解析器会将这些代码左移 4 位后写入 AD9106。电压幅度还取决于板上参考电流及模拟输出电路，不直接用伏特表示。

ENABLE=0 时，目标通道的增益和偏移都写 0；其余字段仍按对应波形规则校验。重新打开时需发送包含全部参数的新命令。这里的关闭表示数字零码输出，不是模拟电源关断。

### 参数换算和限制

设 DAC 采样时钟为 `fDAC`（当前板卡默认 `148.5 MHz`，区别于 FPGA 的 `100 MHz`）：

- 正弦：`RATE=round(fout/fDAC * 2^24)`，范围 `1..0x7FFFFF`。`PHASE=round(角度/360 * 65536) mod 65536`；`4000` 为 90°。
- 三角：`RATE=SAW_STEP`，范围 `1..63`。频率 `fout=fDAC/(32768*RATE)`，只能取这些离散频点；默认步长 4 约为 `1132.965 Hz`。
- 方波：`RATE=cycles`，范围 `1..742`。采样点 `i=0..1484` 的相位为 `(i*cycles) mod 1485`；相位小于 DUTY 时输出 HIGH，否则输出 LOW。`DUTY` 必须满足 `cycles <= DUTY <= 1485-cycles`，确保每段高低电平至少包含一个采样点；近似占空比为 `DUTY/1485`。当 cycles 与 1485 有公因数时，相位格点较少，占空比会进一步量化。名义频率为 `cycles*fDAC/1485`，在当前 `148.5 MHz` DAC 时钟下即 `cycles*100 kHz`，范围 **100 kHz～74.2 MHz，步进 100 kHz**；各边沿可能相差一个采样周期，不能得到完全相等的高低脉宽。频率精度跟随实际 DAC 时钟精度。

初始化时将全局周期扩展到 1485，之后运行时只改方波采样数据，DAC4 的五个波形周期保持不变。若需要任意方波频率，需另行设计全局时基或存储布局。

寄存器位宽、频率公式和写入顺序依据 [AD9106 Rev.C 数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/ad9106.pdf) 的 SPI、SRAM、锯齿波及寄存器说明。

### 可直接发送的示例

正弦：SEQ=1，约 10 MHz、增益 1、偏移 0、相位 90°：

```text
AA 55 01 01 01 04 00 00 00 11 3D 33 40 00 00 00 00 00 00 00 00 00 5A 0D
```

三角：SEQ=1，步长 4、增益 1、偏移 0：

```text
AA 55 01 02 01 04 00 00 00 00 00 04 00 00 00 00 00 00 00 00 00 00 02 0D
```

方波：SEQ=1，5 MHz（RATE=50）、DUTY=743（近似 50%）、高低代码 +1024/-1024：

```text
AA 55 01 03 01 04 00 00 00 00 00 32 00 00 02 E7 04 00 0C 00 00 00 D8 0D
```

方波：SEQ=1，100 kHz（RATE=1）、DUTY=743、高低代码 +1024/-1024：

```text
AA 55 01 03 01 04 00 00 00 00 00 01 00 00 02 E7 04 00 0C 00 00 00 EB 0D
```

## 3. 返回格式和处理时序

回包固定 **8 字节**：

```text
55 AA SEQ CMD STATUS XOR 0D 0A
```

XOR 为 `SEQ ^ CMD ^ STATUS`。例如上述正弦命令成功返回 `55 AA 01 01 00 00 0D 0A`。

| STATUS | 含义 |
| --- | --- |
| `00` | 全部 SPI 写入、RAMUPDATE 写入及更新等待结束，TRIGGER 已重新拉低 |
| `01` | 结束符错误 |
| `02` | 校验错误 |
| `03` | 不支持的指令（包括自定义波形指令） |
| `04` | 参数越界、未使用字段非零或保留位非零 |
| `05` | 半帧超时，默认相邻字节间隔超过 100 ms |
| `06` | 半帧内出现 UART 停止位错误 |
| `07` | 上电初始化尚未完成 |

在 SEQ/CMD 尚未接收到时发生半帧错误，对应回包字段为 0。帧头之外的杂散字节被忽略。错误命令不执行 SPI 写入。

PC 必须使用**发送一帧、等待完整回包、再发下一帧**的模式。没有接收队列，执行命令和发送回包期间收到的输入会丢弃；此时不支持查询或取消。正常命令建议 PC 接收超时设 1 s。上电初始化默认约 100 ms；收到 `07` 后稍后重发。

写入过程为：TRIGGER 拉高 → RUN=0 → 等待停止 →（方波命令设置 MEM_ACCESS，写 1485 点，然后关闭 MEM_ACCESS）→ 写目标参数 → RUN=1 → RAMUPDATE=1 → 等待更新 → TRIGGER 拉低 → 返回成功。方波执行 1492 次 SPI 写入，默认 1 MHz SPI 下约 68 ms 完成（不含请求和返回的串口传输）；正弦 8 次、三角 6 次，约 20 ms 完成。

成功仅表示 FPGA 已完成 SPI 发送和等待，当前设计仍是写操作，不通过 SDO 回读确认寄存器或检测模拟输出。实际 DAC 时钟降低时应增大 `AD9106.RUNTIME_STOP_CYCLES`，使其至少覆盖最长模式周期和停止余量；默认 20 ms 对应当前板卡及支持的最大步长 63。`RUNTIME_UPDATE_CYCLES` 默认 1 µs。

## 4. 接口怎么连

三个新增模块和 `AD9106` 的 `clk` 全部连接现有 **100 MHz** 时钟；`resetn` 全部连接同一低有效、在该时钟域同步释放的复位。所有模块的 `SYS_CLK_HZ` 与实际频率保持一致，接收和返回模块的 `BAUD_RATE` 相同。有效参数应保证 UART 每位至少 4 个系统时钟。

| 源 | 目标 | 位宽 |
| --- | --- | --- |
| 板上串口 RX（PC TX） | `uart_cmd_rx.uart_rx` | 1 |
| `uart_cmd_rx.data` | `ad9106_cmd_parser.rx_data` | 8 |
| `uart_cmd_rx.data_valid` | `ad9106_cmd_parser.rx_valid` | 1 |
| `uart_cmd_rx.frame_error` | `ad9106_cmd_parser.rx_error` | 1 |
| `AD9106.init_done` | `ad9106_cmd_parser.init_done` | 1 |
| `ad9106_cmd_parser.cfg_valid` | `AD9106.cfg_valid` | 1 |
| `ad9106_cmd_parser.cfg_addr` | `AD9106.cfg_addr` | 15 |
| `ad9106_cmd_parser.cfg_wdata` | `AD9106.cfg_wdata` | 16 |
| `ad9106_cmd_parser.cfg_last` | `AD9106.cfg_last` | 1 |
| `AD9106.cfg_ready` | `ad9106_cmd_parser.cfg_ready` | 1 |
| `AD9106.cfg_done` | `ad9106_cmd_parser.cfg_done` | 1 |
| `ad9106_cmd_parser.rsp_valid` | `uart_cmd_tx.rsp_valid` | 1 |
| `ad9106_cmd_parser.rsp_seq` | `uart_cmd_tx.rsp_seq` | 8 |
| `ad9106_cmd_parser.rsp_cmd` | `uart_cmd_tx.rsp_cmd` | 8 |
| `ad9106_cmd_parser.rsp_status` | `uart_cmd_tx.rsp_status` | 8 |
| `uart_cmd_tx.rsp_ready` | `ad9106_cmd_parser.rsp_ready` | 1 |
| `uart_cmd_tx.done` | `ad9106_cmd_parser.rsp_done` | 1 |
| `uart_cmd_tx.uart_tx` | 板上串口 TX（PC RX） | 1 |

`ad9106_cmd_parser.busy`、`uart_cmd_tx.busy` 可连接 ILA/状态灯，也可悬空。`AD9106.init_busy` 现在专指上电初始化状态，运行时写入期间保持 0，初始化完成后 `init_done` 持续为 1。原有 DAC 物理接口仍由 `AD9106` 驱动。

`cfg_valid && cfg_ready` 在上升沿接收一笔写入；解析器保持地址、数据和 last 直到握手，再等待一个时钟宽的 `cfg_done`。`cfg_last` 只标记一条 PC 命令最后的 RAMUPDATE 写入。`rsp_valid && rsp_ready` 接收一份完整回包数据，`uart_cmd_tx.done` 在最后停止位发送完毕后输出一个时钟脉冲。所有握手均为同一时钟域。

若暂时只运行原 demo，将新增 `AD9106.cfg_valid/cfg_last/cfg_addr/cfg_wdata` 输入接 0。重新打包 AD9106 IP 或刷新 BD 模块引用，才能看到新增接口；当前已生成的 IP wrapper 不会自行更新。串口引脚位置需在用户接顶层后按实际板卡补入 XDC。

在当前打开的 Vivado 工程 Tcl Console 运行以下语句，可把新文件加入工程；脚本不会改顶层或仿真顶层：

```tcl
source {E:/vivado project/AD9106/tools/add_uart_control.tcl}
```

## 5. PC 工具与仿真

`tools/ad9106_uart.py` 可生成完整十六进制指令；加 `--port` 可通过 pyserial 发串口并校验返回。

```powershell
python tools/ad9106_uart.py sine --frequency 10000000 --phase 90
python tools/ad9106_uart.py triangle --step 4
python tools/ad9106_uart.py square --cycles 50 --duty 50 --high 1024 --low -1024
python tools/ad9106_uart.py square --frequency 100000 --port COM3
python tools/ad9106_uart.py sine --frequency 1000000 --gain 0.5 --port COM3
```

串口发送需要 `python -m pip install pyserial`；仅生成帧不依赖第三方库。`--frequency` 也支持三角和方波，工具会打印量化后的实际名义频率。`--gain/--offset/--seq/--off` 可用于三种波形。

模块级集成仿真只在 testbench 中连接模块，不修改生产顶层。运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_uart_control.ps1
```

测试覆盖初始化 3011 次 SPI 写入、DAC4 原波形的五次重复、初始化期间拒绝命令、三种波形的寄存器、方波 1485 个采样点及整帧周期数（100/200/300 kHz、5 MHz、74.2 MHz）、关闭输出、错误回包、超时及停止位错误恢复、边界参数和 DAC4 区域保护。仿真为加速运行使用较小分频及等待参数，板卡默认参数由 RTL 给出。

独立综合检查：

```powershell
& E:/Xilinx/Vivado/2023.2/bin/vivado.bat -mode batch -source tools/check_uart_synth.tcl
```

脚本检查三个新模块和 `AD9106`，不修改已有工程。日志和报告放在 `.uart_sim/`。这属于 RTL 仿真与独立综合验证，尚未进行板上串口和 DAC 模拟输出测试。

当前已接线顶层的完整功能回归、厂商时钟专项、全新顶层综合及证据图表见 [项目验证报告](PROJECT_VERIFICATION.md)。
