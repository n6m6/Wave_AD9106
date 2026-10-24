# 23 种发放模式的 Vin / Vgate 分类

从用户提供的 HTML 自动提取，包含 4 种拓扑 × 23 种模式及全部主例/对照。实验是否产生目标发放，以原文判定为准；本工程生成的是输入激励。

variant 从 0 开始；不同实验曲线分别编号。sequence 表示同一输入中的多幅度/近远间隔序列；low/mid/high、near/far/single、first/second 可分别选择。

原始 CSV、RAW、input.json 未随 HTML 提供。默认时序为图文重建模板，不能声称精确重现实验。

## 拓扑 3 / 01 Tonic spiking

01 Tonic spiking — 持续发放 — 做到

Vin方波重复两次，工作窗口内Gate恒定；重复发放不由逐次Gate触发。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular01 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 3 / 02 Phasic spiking

02 Phasic spiking — 相位性单发 — 做到

Gate恒压，每次输入起始单发。③低Gate下单发后电流约0.058 mA，未把它解释成长期低阻锁存。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular02 | [0.0, 4.3] | [0.0, 1.0] |

## 拓扑 3 / 03 Tonic bursting

03 Tonic bursting — 持续簇发 — 做到*

每个Vin长窗口内，Gate为三段22 μs长方波，每段自然产生多个脉冲；簇节律由Gate规定。

Vin：`positive_window`；Vgate：`three_gate_windows`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular03 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 3 / 04 Phasic bursting

04 Phasic bursting — 相位性簇发 — 做到*

仅输入开始时使能22 μs，之后Gate降为0；长方波形成起始簇。

Vin：`positive_window`；Vgate：`onset_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular04 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 3 / 05 Mixed mode

05 Mixed mode — 混合模式 — 做到*

Gate直线下降，ISI逐渐增大。前70 μs下降后保持低值，呈快到慢变化，未插入归零边沿。

Vin：`positive_window`；Vgate：`ramp_or_step_hold`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular05_0 | [0.0, 4.3] | [0.0, 3.0] |

## 拓扑 3 / 06 Spike frequency adaptation

06 Spike frequency adaptation — 发放频率适应 — 做到*

Gate直线下降，ISI逐渐增大。整段140 μs线性下降。

Vin：`positive_window`；Vgate：`ramp`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular06_0 | [0.0, 4.3] | [0.0, 3.0] |

## 拓扑 3 / 07 Class I excitability

07 Class I excitability — I类兴奋性 — 做到*

Vin上升斜坡跨过发放阈值，局部放大另列。第一层仅纳入越阈展示；没有证明Class I的阈值频率趋零。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular07 | [0.0, 6.0] | [0.0, 2.4] |

## 拓扑 3 / 08 Class II excitability

08 Class II excitability — II类兴奋性 — 未做到

本轮未获得足够的有限频率起振对照，不借用其它拓扑结果。 展示激励：与⑦08相同的近阈值双幅度输入；该参考本身也未证实Class II。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m08_0 | [0.0, 3.5082] | [0.0, 6.0] |
| 1 | 主例 03_atlas_m08_1 | [0.0, 3.5085] | [0.0, 6.0] |

## 拓扑 3 / 09 Spike latency

09 Spike latency — 首脉冲延迟 — 做到

恒定Gate；不同幅度、相同短输入窗口均单发，比较首脉冲延迟；局部放大另列。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular09_v3.3 | [0.0, 3.3] | [0.0, 1.0] |
| 1 | 主例 03_regular09_v3.6 | [0.0, 3.6] | [0.0, 1.0] |
| 2 | 主例 03_regular09_v4.3 | [0.0, 4.3] | [0.0, 1.0] |

## 拓扑 3 / 10 Subthreshold oscillations

10 Subthreshold oscillations — 阈下振荡 — 未做到

按用户指示，微小/受迫阈下波动不计实现；图中仍展示对应测试的实际响应。 展示激励：沿用⑤10正弦Gate的阈下测试；此参考也未通过自主阈下振荡目标。

Vin：`positive_window`；Vgate：`sine_bias`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m10_0 | [0.0, 4.3] | [0.0, 1.59999] |

## 拓扑 3 / 11 Resonator

11 Resonator — 共振器 — 未做到

照搬⑤正弦Gate参数后，高低输入频率都逐次响应，单输入也有效，未得到累计与频率选择。 展示激励：与⑤11成功参考相同的Vin/Gate时序与CMEM；拓扑仍为③。

Vin：`pulse_train`；Vgate：`sine_or_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m11_0 | [0.0, 6.0] | [0.0, 2.49993] |
| 1 | 主例 03_atlas_m11_1 | [0.0, 6.0] | [0.0, 2.49993] |
| 2 | 对照 03_ground_verify_r2_m11_g2.5_w1.8_p6_fine | [0.0, 6.0] | [0.0, 2.49993] |
| 3 | 对照 03_ground_verify_r2_m11_g2.5_w1.8_p12_fine | [0.0, 6.0] | [0.0, 2.49993] |
| 4 | 对照 03_ground_verify_r2_m11_single | [0.0, 6.0] | [0.0, 2.49993] |

## 拓扑 3 / 12 Integrator

12 Integrator — 积分器 — 未做到

接地膜电容版本未得到近间隔累计、远间隔不发的目标；短输入扫描出现近邻合并，但远间隔各自可发，不能算积分。 展示激励：与⑤12成功参考相同的Vin/Gate时序与CMEM；拓扑仍为③。

Vin：`near_far_pulses`；Vgate：`constant`；分项：`sequence, near, far, single`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m12_0 | [0.0, 5.5] | [0.0, 2.2] |
| 1 | 对照 03_ground_verify_r2_m12 | [0.0, 5.5] | [0.0, 2.2] |
| 2 | 对照 03_ground_verify_r2_m12_single | [0.0, 5.5] | [0.0, 2.2] |
| 3 | 对照 03_integration_c1n_w0.05_v3.3 | [0.0, 3.3] | [0.0, 2.4] |

## 拓扑 3 / 13 Rebound spike

13 Rebound spike — 反弹单发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：四拓扑统一：0→−5 V→0，恒Gate=6 V；在负脉冲撤去后检验单发与簇发，没有重新施加正Vin。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 对照 03_negative_b4.3_n-5_g4 | [-5.0, 4.3] | [0.0, 4.0] |
| 2 | 对照 03_rebound_bias_only | [0.0, 4.3] | [0.0, 4.0] |

## 拓扑 3 / 14 Rebound burst

14 Rebound burst — 反弹簇发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：与13使用同一负输入撤去测试；检查释放后是否形成有限脉冲簇。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 3 / 15 Threshold variability

15 Threshold variability — 阈值可变性 — 做到

同幅Vin配合不同高度、对齐的长Gate方波，分别不发、少发、多发。③使用现有CMEM=0.1 nF、Vin上升时间2 μs；其余项目通常1 nF。 无Gate记忆电容。

Vin：`positive_window`；Vgate：`three_gate_levels`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_quantity_c.1n | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 3 / 16 Bistability

16 Bistability — 双稳态 — 做到*

Gate先恒定，Vin方波启动发放；Vin仍高时一个正向Gate方波停止重复尖峰。停止段进入低阻直流，不代表电流归零；不宣称同偏置双吸引子。

Vin：`positive_window`；Vgate：`stop_gate_step`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_final16_gate_stop | [0.0, 4.3] | [0.0, 4.0] |

## 拓扑 3 / 17 Depolarizing after-potential

17 Depolarizing after-potential — 去极化后电位 — 未做到

恒定正Vin和Gate平台内没有有效负向输出；启动、撤去和Gate边沿尖峰均排除。 展示激励：与⑦17相同的Vin/Gate恒定输入；仅平台内负电流属于目标，启动与撤去尖峰不算。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m17_0 | [0.0, 4.0] | [0.0, 2.0] |
| 1 | 对照 03_regular17_g2.4 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 3 / 18 Accommodation

18 Accommodation — 适应性 — 做到

③恒定Gate=1 V，快上升发一次、80 μs慢上升在上升及保持窗口内不发；单发后电流约0.06 mA。两者撤去输入时仍有反向瞬态，图中完整保留，不计作正向发放。

Vin：`fast_slow_ramp`；Vgate：`constant_or_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular18_rise0.02 | [0.0, 4.3] | [0.0, 1.0] |
| 1 | 主例 03_regular18_rise80 | [0.0, 4.3] | [0.0, 1.0] |

## 拓扑 3 / 19 Inhibition-induced spiking

19 Inhibition-induced spiking — 抑制诱导发放 — 未做到

严格负输入下未获得持续反向脉冲，连续反向直流不算持续发放。 展示激励：沿用⑦19成功参考的Vin/Gate时序、CMEM；⑥同时采用相同RLIMIT=3.3kΩ，③⑤没有此元件。

Vin：`negative_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m19_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 对照 03_negative_b4.3_n-5_g4 | [-5.0, 4.3] | [0.0, 4.0] |

## 拓扑 3 / 20 Inhibition-induced bursting

20 Inhibition-induced bursting — 抑制诱导簇发 — 未做到

严格负输入下未找到目标反向簇发。 展示激励：沿用⑦20成功参考的Vin/Gate时序、CMEM；⑥同时采用相同RLIMIT=3.3kΩ，③⑤没有此元件。

Vin：`negative_bursts`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_atlas_m20_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 3 / 21 All-or-none response

21 All-or-none response — 全或无响应 — 做到

恒定Gate，不同幅度Vin展示不发与发放；调低后续持续电流。③实际Gate=1 V（旧实验ID不是参数值），完整参数以input.json为准。

Vin：`multi_level_pulses`；Vgate：`constant`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular21_g1.7 | [0.0, 4.3] | [0.0, 1.0] |

## 拓扑 3 / 22 Refractory period

22 Refractory period — 不应期 — 做到*

Gate恒压；单个探针各自能触发，短间隔对只产生一次Mott开关、稍长间隔产生两次。附局部放大。仅证明未复位电流合并与恢复，不宣称严格绝对不应期；间隔从下降沿起点计，含20 ns下降时间。

Vin：`paired_probes`；Vgate：`constant`；分项：`pair, first, second`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular22_gap0.1 | [0.0, 8.0] | [0.0, 6.0] |
| 1 | 主例 03_regular22_gap0.5 | [0.0, 8.0] | [0.0, 6.0] |
| 2 | 对照 03_final22_single1 | [0.0, 8.0] | [0.0, 6.0] |
| 3 | 对照 03_final22_single2 | [0.0, 8.0] | [0.0, 6.0] |

## 拓扑 3 / 23 Depolarization block

23 Depolarization block — 去极化阻滞 — 做到

恒定Gate，Vin上升—平台—归零。上升途中发放，强输入段转为连续低阻导通；阻断的是重复尖峰而不是直流。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 03_regular23 | [0.0, 12.0] | [0.0, 3.5] |

## 拓扑 5 / 01 Tonic spiking

01 Tonic spiking — 持续发放 — 做到

Vin方波重复两次，工作窗口内Gate恒定；重复发放不由逐次Gate触发。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular01 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 5 / 02 Phasic spiking

02 Phasic spiking — 相位性单发 — 做到

Gate恒压，每次输入起始单发。单发后维持低阻直流，属于用户原先指定的起始单发操作目标。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular02 | [0.0, 4.3] | [0.0, 4.0] |

## 拓扑 5 / 03 Tonic bursting

03 Tonic bursting — 持续簇发 — 做到*

每个Vin长窗口内，Gate为三段22 μs长方波，每段自然产生多个脉冲；簇节律由Gate规定。

Vin：`positive_window`；Vgate：`three_gate_windows`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular03 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 5 / 04 Phasic bursting

04 Phasic bursting — 相位性簇发 — 做到*

仅输入开始时使能22 μs，之后Gate降为0；长方波形成起始簇。

Vin：`positive_window`；Vgate：`onset_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular04 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 5 / 05 Mixed mode

05 Mixed mode — 混合模式 — 做到*

Gate直线下降，ISI逐渐增大。前70 μs下降后保持低值，呈快到慢变化，未插入归零边沿。

Vin：`positive_window`；Vgate：`ramp_or_step_hold`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular05_0 | [0.0, 4.3] | [0.0, 3.0] |

## 拓扑 5 / 06 Spike frequency adaptation

06 Spike frequency adaptation — 发放频率适应 — 做到*

Gate直线下降，ISI逐渐增大。整段140 μs线性下降。

Vin：`positive_window`；Vgate：`ramp`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular06_0 | [0.0, 4.3] | [0.0, 3.0] |

## 拓扑 5 / 07 Class I excitability

07 Class I excitability — I类兴奋性 — 做到*

Vin上升斜坡跨过发放阈值，局部放大另列。第一层仅纳入越阈展示；没有证明Class I的阈值频率趋零。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular07 | [0.0, 6.0] | [0.0, 2.4] |

## 拓扑 5 / 08 Class II excitability

08 Class II excitability — II类兴奋性 — 未做到

本轮未获得足够的有限频率起振对照，不借用其它拓扑结果。 展示激励：与⑦08相同的近阈值双幅度输入；该参考本身也未证实Class II。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m08_0 | [0.0, 3.5082] | [0.0, 6.0] |
| 1 | 主例 05_atlas_m08_1 | [0.0, 3.5085] | [0.0, 6.0] |

## 拓扑 5 / 09 Spike latency

09 Spike latency — 首脉冲延迟 — 做到

恒定Gate；不同幅度、相同短输入窗口均单发，比较首脉冲延迟；局部放大另列。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_r2_m09_4.1 | [0.0, 4.1] | [0.0, 2.2] |
| 1 | 主例 05_r2_m09_4.3 | [0.0, 4.3] | [0.0, 2.2] |
| 2 | 主例 05_r2_m09_4.8 | [0.0, 4.8] | [0.0, 2.2] |

## 拓扑 5 / 10 Subthreshold oscillations

10 Subthreshold oscillations — 阈下振荡 — 未做到

按用户指示，微小/受迫阈下波动不计实现；图中仍展示对应测试的实际响应。

Vin：`positive_window`；Vgate：`sine_bias`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_m10_g1.3_a0.3 | [0.0, 4.3] | [0.0, 1.59999] |
| 1 | 对照 05_m10_flat_control | [0.0, 4.3] | [0.0, 1.3] |

## 拓扑 5 / 11 Resonator

11 Resonator — 共振器 — 做到*

输入：Vin=6V、宽1.8μs、10次；Gate为0–2.5V正弦，周期12μs；对齐/错相。结果：每组恰好 10 个 6 V、宽 1.8 μs 方波。Gate 为 0–2.5 V、周期 12 μs 正弦；错相高频输入 0 次，对齐低频输入 4 次，首次需 3 个输入；单输入对照不发。 同拓扑历史RAW复用，采样仍10Ω。

Vin：`pulse_train`；Vgate：`sine_or_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_r2_m11_g2.5_w1.8_p6_fine | [0.0, 6.0] | [0.0, 2.49993] |
| 1 | 主例 05_r2_m11_g2.5_w1.8_p12_fine | [0.0, 6.0] | [0.0, 2.49993] |
| 2 | 对照 05_r2_m11_single | [0.0, 6.0] | [0.0, 2.49993] |

## 拓扑 5 / 12 Integrator

12 Integrator — 积分器 — 做到

输入：Vin=5.5V、宽1.4μs、每组6次，空隙4/8μs；Gate=2.2V恒定。结果：两组均为 6 个 5.5 V、宽 1.4 μs 输入。前组空隙 4 μs：1 次；后组空隙 8 μs：0 次。空隙按前一脉冲下降开始到下一上升开始计算，边沿为 0.02 μs。 同拓扑历史RAW复用，采样仍10Ω。

Vin：`near_far_pulses`；Vgate：`constant`；分项：`sequence, near, far, single`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_r2_m12 | [0.0, 5.5] | [0.0, 2.2] |
| 1 | 对照 05_r2_m12_single | [0.0, 5.5] | [0.0, 2.2] |

## 拓扑 5 / 13 Rebound spike

13 Rebound spike — 反弹单发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：四拓扑统一：0→−5 V→0，恒Gate=6 V；在负脉冲撤去后检验单发与簇发，没有重新施加正Vin。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 对照 05_negative_b4.3_n-5_g4 | [-5.0, 4.3] | [0.0, 4.0] |
| 2 | 对照 05_rebound_bias_only | [0.0, 4.3] | [0.0, 4.0] |

## 拓扑 5 / 14 Rebound burst

14 Rebound burst — 反弹簇发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：与13使用同一负输入撤去测试；检查释放后是否形成有限脉冲簇。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 5 / 15 Threshold variability

15 Threshold variability — 阈值可变性 — 做到

同幅Vin配合不同高度、对齐的长Gate方波，分别不发、少发、多发。 无Gate记忆电容。

Vin：`positive_window`；Vgate：`three_gate_levels`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular15 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 5 / 16 Bistability

16 Bistability — 双稳态 — 做到*

Gate先恒定，Vin方波启动发放；Vin仍高时一个正向Gate方波停止重复尖峰。停止段进入低阻直流，不代表电流归零；不宣称同偏置双吸引子。

Vin：`positive_window`；Vgate：`stop_gate_step`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_final16_gate_stop | [0.0, 4.3] | [0.0, 4.0] |

## 拓扑 5 / 17 Depolarizing after-potential

17 Depolarizing after-potential — 去极化后电位 — 未做到

恒定正Vin和Gate平台内没有有效负向输出；启动、撤去和Gate边沿尖峰均排除。 展示激励：与⑦17相同的Vin/Gate恒定输入；仅平台内负电流属于目标，启动与撤去尖峰不算。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m17_0 | [0.0, 4.0] | [0.0, 2.0] |
| 1 | 对照 05_regular17_g2.4 | [0.0, 4.3] | [0.0, 2.4] |

## 拓扑 5 / 18 Accommodation

18 Accommodation — 适应性 — 做到*

相对每次Vin起点使用相同8 μs长Gate使能窗口，快速输入有发放、慢上升输入无发放；窗口关闭降低后续直流。这是外部门控的快慢选择，不是已证明的内源适应。

Vin：`fast_slow_ramp`；Vgate：`constant_or_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_final18_window_rise0.02 | [0.0, 4.3] | [0.0, 2.2] |
| 1 | 主例 05_final18_window_rise80 | [0.0, 4.3] | [0.0, 2.2] |

## 拓扑 5 / 19 Inhibition-induced spiking

19 Inhibition-induced spiking — 抑制诱导发放 — 未做到

严格负输入下未获得持续反向脉冲，连续反向直流不算持续发放。 展示激励：沿用⑦19成功参考的Vin/Gate时序、CMEM；⑥同时采用相同RLIMIT=3.3kΩ，③⑤没有此元件。

Vin：`negative_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m19_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 对照 05_negative_b4.3_n-5_g4 | [-5.0, 4.3] | [0.0, 4.0] |

## 拓扑 5 / 20 Inhibition-induced bursting

20 Inhibition-induced bursting — 抑制诱导簇发 — 未做到

严格负输入下未找到目标反向簇发。 展示激励：沿用⑦20成功参考的Vin/Gate时序、CMEM；⑥同时采用相同RLIMIT=3.3kΩ，③⑤没有此元件。

Vin：`negative_bursts`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_atlas_m20_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 5 / 21 All-or-none response

21 All-or-none response — 全或无响应 — 做到

恒定Gate，不同幅度Vin展示不发与发放；采用较低后续电流的工作点，不把脉冲间的低电流中位数当静态电流。

Vin：`multi_level_pulses`；Vgate：`constant`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular21_g1.7 | [0.0, 5.0] | [0.0, 1.7] |

## 拓扑 5 / 22 Refractory period

22 Refractory period — 不应期 — 做到*

Gate恒压；单个探针各自能触发，短间隔对只产生一次Mott开关、稍长间隔产生两次。附局部放大。仅证明未复位电流合并与恢复，不宣称严格绝对不应期；间隔从下降沿起点计，含20 ns下降时间。

Vin：`paired_probes`；Vgate：`constant`；分项：`pair, first, second`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular22_gap0.1 | [0.0, 8.0] | [0.0, 6.0] |
| 1 | 主例 05_regular22_gap0.5 | [0.0, 8.0] | [0.0, 6.0] |
| 2 | 对照 05_final22_single1 | [0.0, 8.0] | [0.0, 6.0] |
| 3 | 对照 05_final22_single2 | [0.0, 8.0] | [0.0, 6.0] |

## 拓扑 5 / 23 Depolarization block

23 Depolarization block — 去极化阻滞 — 做到

恒定Gate，Vin上升—平台—归零。上升途中发放，强输入段转为连续低阻导通；阻断的是重复尖峰而不是直流。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 主例 05_regular23 | [0.0, 12.0] | [0.0, 3.5] |

## 拓扑 6 / 01 Tonic spiking

01 Tonic spiking — 持续发放 — 做到

恒Gate=6.8V，Vin=5V两段100μs平台；两轮各45次持续发放。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular01 | [0.0, 5.0] | [0.0, 6.8] |

## 拓扑 6 / 02 Phasic spiking

02 Phasic spiking — 相位性单发 — 做到

恒Gate=8.8V，Vin=5V两段平台；两轮各1次起始单发，随后低阻直流保持。仅按原指定起始单发操作判定。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular02 | [0.0, 5.0] | [0.0, 8.8] |

## 拓扑 6 / 03 Tonic bursting

03 Tonic bursting — 持续簇发 — 做到*

Vin长平台内Gate为6.8V的三段22μs长方波，每段自然重复发放，两轮各30次；簇节律来自外部Gate。

Vin：`positive_window`；Vgate：`three_gate_windows`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular03 | [0.0, 5.0] | [0.0, 6.8] |

## 拓扑 6 / 04 Phasic bursting

04 Phasic bursting — 相位性簇发 — 做到*

Vin仍保持时，仅起始22μs开放Gate=6.8V，形成两轮各10次的起始簇；由外部Gate窗口形成。

Vin：`positive_window`；Vgate：`onset_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular04 | [0.0, 5.0] | [0.0, 6.8] |

## 拓扑 6 / 05 Mixed mode

05 Mixed mode — 混合模式 — 做到*

Gate在前70μs从7.8V线性降至6.3V，随后保持；两轮各57次，ISI由约2.02μs增至约2.82μs并维持慢发。原快到慢操作恢复，不宣称内源混合模态。

Vin：`positive_window`；Vgate：`ramp_or_step_hold`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_final05_g7_5.5 | [0.0, 5.0] | [0.0, 7.8] |

## 拓扑 6 / 06 Spike frequency adaptation

06 Spike frequency adaptation — 发放频率适应 — 做到*

Gate在140μs内由7.8V线性降至6.3V；两轮各64次，ISI逐渐增大，属于外部Gate诱导减速。

Vin：`positive_window`；Vgate：`ramp`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_final06_g7_5.5 | [0.0, 5.0] | [0.0, 7.8] |

## 拓扑 6 / 07 Class I excitability

07 Class I excitability — I类兴奋性 — 做到*

恒Gate=6.8V，Vin上升斜坡越阈后发放，两轮各19次。仅越阈操作候选，未证明Class I阈值频率趋零。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular07 | [0.0, 5.0] | [0.0, 6.8] |

## 拓扑 6 / 08 Class II excitability

08 Class II excitability — II类兴奋性 — 未做到

本轮未获得足够的有限频率起振对照，不借用其它拓扑结果。 展示激励：与⑦08相同的近阈值双幅度输入；该参考本身也未证实Class II。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m08_0 | [0.0, 3.5082] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 06_atlas_m08_1 | [0.0, 3.5085] | [0.0, 6.0] |

## 拓扑 6 / 09 Spike latency

09 Spike latency — 首脉冲延迟 — 做到

恒Gate=7.3V；Vin=4/4.5/5V、相同约3μs输入均每轮单发，比较幅度依赖的首脉冲延迟。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_r_delay_v4 | [0.0, 4.0] | [0.0, 7.3] |
| 1 | 橙实线 · 主例 06_r9_v4.5_matched | [0.0, 4.5] | [0.0, 7.3] |
| 2 | 灰实线 · 主例 06_r_delay_v5 | [0.0, 5.0] | [0.0, 7.3] |

## 拓扑 6 / 10 Subthreshold oscillations

10 Subthreshold oscillations — 阈下振荡 — 未做到

保留B=−5V原协议测试；外部Gate产生的膜电位变化不能证明内源阈下振荡，本次未验证。

Vin：`positive_window`；Vgate：`sine_bias`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_r_m10 | [0.0, 5.0] | [0.0, 5.1] |

## 拓扑 6 / 11 Resonator

11 Resonator — 共振器 — 做到*

Vin=6V、宽约0.77μs含边沿，10个输入；Gate为0–8V、周期2μs的持续正弦。匹配周期2μs发4次，首次第三输入后；密集错相/单输入/无输入均0。属于外部节律输入选择，不宣称内源共振。

Vin：`pulse_train`；Vgate：`sine_or_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_r11_v6_g8_aligned | [0.0, 6.0] | [0.0, 8.0] |
| 1 | 橙实线 · 主例 06_r11_v6_g8_offset | [0.0, 6.0] | [0.0, 8.0] |
| 2 | 灰实线 · 对照 06_r11_v6_g8_aligned_single | [0.0, 6.0] | [0.0, 8.0] |
| 3 | 紫实线 · 对照 06_r11_no_input | [0.0, 0.0] | [0.0, 8.0] |

## 拓扑 6 / 12 Integrator

12 Integrator — 积分器 — 做到*

Vin=5V、宽约0.47μs含边沿、6次；Gate=7.1V、宽约0.43μs同步关闭。周期1.2μs积累1次，周期15μs不发，两轮重复；单输入与恒Gate对照均0。同步Gate关闭是必要协议条件。

Vin：`near_far_pulses`；Vgate：`constant_with_synchronous_notches`；分项：`sequence, near, far, single`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_r12_w0.45_g6.5 | [0.0, 5.0] | [0.0, 7.1] |
| 1 | 橙实线 · 对照 06_r12_w0.45_g6.5_single | [0.0, 5.0] | [0.0, 7.1] |
| 2 | 灰实线 · 对照 06_r12_fixed_gate | [0.0, 5.0] | [0.0, 7.1] |

## 拓扑 6 / 13 Rebound spike

13 Rebound spike — 反弹单发 — 未做到

B=−5V负输入撤回0后，两个释放窗口均无反弹发放；负平台内发放或返回正偏置不能计作反弹。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 06_negative_b5_n-5_g8 | [-5.0, 5.0] | [0.0, 8.0] |
| 2 | 灰实线 · 对照 06_rebound_bias_only | [0.0, 5.0] | [0.0, 8.0] |

## 拓扑 6 / 14 Rebound burst

14 Rebound burst — 反弹簇发 — 未做到

B=−5V负输入撤回0后未出现反弹簇发，本次测试不支持。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 6 / 15 Threshold variability

15 Threshold variability — 阈值可变性 — 做到

Vin同为5V；Gate=5.8/6.3/7.3V的长窗口对应0/10/14次，两轮重复；展示Gate调节可发条件。

Vin：`positive_window`；Vgate：`three_gate_levels`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular15 | [0.0, 5.0] | [0.0, 7.3] |

## 拓扑 6 / 16 Bistability

16 Bistability — 双稳态 — 做到*

Vin=5V启动、Gate=6.8V时重复发放；Vin持续期间Gate升至8.8V，重复尖峰停止，转为低阻直流。两轮窗口计数20/0。不是同偏置双吸引子证明。

Vin：`positive_window`；Vgate：`stop_gate_step`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_final16_gate_stop | [0.0, 5.0] | [0.0, 8.8] |

## 拓扑 6 / 17 Depolarizing after-potential

17 Depolarizing after-potential — 去极化后电位 — 未做到

B=−5V原两组未得到发放后去极化后电位的证据；不以负电流替代功能判据。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m17_0 | [0.0, 4.0] | [0.0, 2.0] |
| 1 | 橙实线 · 对照 06_regular17_g6 | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 6 / 18 Accommodation

18 Accommodation — 适应性 — 做到*

相对各Vin起点使用同样8μs、6.3V Gate窗口，快上升两轮各2次，80μs慢上升均0。恢复外部门控快慢选择操作；不证明恒Gate下内源Accommodation，*仅计入操作展示。

Vin：`fast_slow_ramp`；Vgate：`constant_or_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_final18_window_rise0.02 | [0.0, 5.0] | [0.0, 6.3] |
| 1 | 橙实线 · 主例 06_final18_window_rise80 | [0.0, 5.0] | [0.0, 6.3] |

## 拓扑 6 / 19 Inhibition-induced spiking

19 Inhibition-induced spiking — 抑制诱导发放 — 做到

Vin=−5V、Gate=6V、Rlimit=3.3kΩ、C=1nF，B=−5V，两轮60μs负平台各14次重复发放。1/0.5ns复核计数一致，无输入对照0。

Vin：`negative_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m19_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 06_negative_b5_n-5_g8 | [-5.0, 5.0] | [0.0, 8.0] |

## 拓扑 6 / 20 Inhibition-induced bursting

20 Inhibition-induced bursting — 抑制诱导簇发 — 做到*

同负向参数，3个22μs负输入段每段5次，每轮15次，两轮重复。1/0.5ns计数一致；由外部输入分段形成簇发，不宣称恒定负输入下内源簇发。

Vin：`negative_bursts`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_atlas_m20_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 6 / 21 All-or-none response

21 All-or-none response — 全或无响应 — 做到

恒Gate=6.3V；Vin=3/4.7/5V短输入对应0/1/1次，两轮重复。展示阈下无尖峰与阈上全幅尖峰。

Vin：`multi_level_pulses`；Vgate：`constant`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_final21_width3.2 | [0.0, 5.0] | [0.0, 6.3] |

## 拓扑 6 / 22 Refractory period

22 Refractory period — 不应期 — 做到*

恒Gate=8.8V；单输入分别1次，短间隔0.1μs双输入合并为1次，0.3μs恢复2次。间隔从下降沿起点计；仅证明未复位电流合并与恢复，不宣称严格绝对不应期。

Vin：`paired_probes`；Vgate：`constant`；分项：`pair, first, second`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular22_gap0.1 | [0.0, 5.0] | [0.0, 8.8] |
| 1 | 橙实线 · 主例 06_regular22_gap0.3 | [0.0, 5.0] | [0.0, 8.8] |
| 2 | 灰实线 · 对照 06_final22_single1 | [0.0, 5.0] | [0.0, 8.8] |
| 3 | 紫实线 · 对照 06_final22_single2 | [0.0, 5.0] | [0.0, 8.8] |

## 拓扑 6 / 23 Depolarization block

23 Depolarization block — 去极化阻滞 — 做到

恒Gate=6.3V，Vin斜坡升至8V并保持；上升途中两轮各9次，强输入段低阻直流保持。阻断的是重复尖峰，不是电流归零。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 06_regular23 | [0.0, 8.0] | [0.0, 6.3] |

## 拓扑 7 / 01 Tonic spiking

01 Tonic spiking — 持续发放 — 做到

Vin方波重复两次，工作窗口内Gate恒定；重复发放不由逐次Gate触发。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular01 | [0.0, 4.0] | [0.0, 6.0] |

## 拓扑 7 / 02 Phasic spiking

02 Phasic spiking — 相位性单发 — 做到

Gate恒压，每次输入起始单发。单发后维持低阻直流，属于用户原先指定的起始单发操作目标。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular02 | [0.0, 5.0] | [0.0, 8.0] |

## 拓扑 7 / 03 Tonic bursting

03 Tonic bursting — 持续簇发 — 做到*

每个Vin长窗口内，Gate为三段22 μs长方波，每段自然产生多个脉冲；簇节律由Gate规定。

Vin：`positive_window`；Vgate：`three_gate_windows`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular03 | [0.0, 4.0] | [0.0, 6.0] |

## 拓扑 7 / 04 Phasic bursting

04 Phasic bursting — 相位性簇发 — 做到*

仅输入开始时使能22 μs，之后Gate降为0；长方波形成起始簇。

Vin：`positive_window`；Vgate：`onset_gate_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular04 | [0.0, 4.0] | [0.0, 6.0] |

## 拓扑 7 / 05 Mixed mode

05 Mixed mode — 混合模式 — 做到*

Gate由3.6 V直接切到6 V，发放间隔约2.09→4.54 μs，每窗21次，两个输入窗均成立。 恢复同拓扑已有成功波形，支持*表示第一层外部调制效果；不是内源混合模式/适应机制证明。下降Gate未成功只限制那一种调法，不否定拓扑对快慢发放的支持。

Vin：`positive_window`；Vgate：`ramp_or_step_hold`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_retune_c05_fine | [0.0, 8.0] | [0.0, 6.0] |

## 拓扑 7 / 06 Spike frequency adaptation

06 Spike frequency adaptation — 发放频率适应 — 做到*

Gate从3.4 V线性升到6 V，间隔由约0.37增至4.54 μs；初段包含小幅高频开关，完整电流保留。 恢复同拓扑已有成功波形，支持*表示第一层外部调制效果；不是内源混合模式/适应机制证明。下降Gate未成功只限制那一种调法，不否定拓扑对快慢发放的支持。

Vin：`positive_window`；Vgate：`ramp`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_retune_c06_g3.4_fine | [0.0, 8.0] | [0.0, 6.0] |

## 拓扑 7 / 07 Class I excitability

07 Class I excitability — I类兴奋性 — 做到*

Vin上升斜坡跨过发放阈值，局部放大另列。第一层仅纳入越阈展示；没有证明Class I的阈值频率趋零。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular07 | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 7 / 08 Class II excitability

08 Class II excitability — II类兴奋性 — 未做到

原近阈值两个恒压输入的对照不足以确认Class II兴奋性；按2026-10-09复核取消成功判定，数据仅作未通过证据保留。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_onset_final_v3.5082 | [0.0, 3.5082] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 07_onset_final_v3.5085 | [0.0, 3.5085] | [0.0, 6.0] |
| 2 | 灰实线 · 主例 07_near_onset_v3.51 | [0.0, 3.51] | [0.0, 6.0] |

## 拓扑 7 / 09 Spike latency

09 Spike latency — 首脉冲延迟 — 做到

恒定Gate；不同幅度、相同短输入窗口均单发，比较首脉冲延迟；局部放大另列。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_seed_b09_delay4 | [0.0, 4.0] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 07_seed_b09_delay4.5 | [0.0, 4.5] | [0.0, 6.0] |
| 2 | 灰实线 · 主例 07_seed_b09_delay5 | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 7 / 10 Subthreshold oscillations

10 Subthreshold oscillations — 阈下振荡 — 未做到

按用户指示，微小/受迫阈下波动不计实现；图中仍展示对应测试的实际响应。

Vin：`positive_window`；Vgate：`sine_bias`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_seed_b10 | [0.0, 3.0] | [0.0, 4.99979] |

## 拓扑 7 / 11 Resonator

11 Resonator — 共振器 — 未做到

快速逐周期匹配42组尚未同时满足全部判据。旧慢Gate窗口不计共振；Gate对泄漏速度的控制另作机制展示。

Vin：`pulse_train`；Vgate：`gate_windows_or_constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_select_v6_w0.5_fast0_half | [0.0, 6.0] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 07_select_v6_w0.5_fast1_half | [0.0, 6.0] | [0.0, 6.0] |
| 2 | 灰实线 · 对照 07_select_control_single | [0.0, 6.0] | [0.0, 6.0] |
| 3 | 紫实线 · 对照 07_select_control_none | [0.0, 0.0] | [0.0, 6.0] |
| 4 | 蓝虚线 · 对照 07_select_control_early_gate | [0.0, 6.0] | [0.0, 6.0] |
| 5 | 橙虚线 · 对照 07_select_control_repeat | [0.0, 6.0] | [0.0, 6.0] |
| 6 | 灰虚线 · 对照 07_select_constant_gate | [0.0, 6.0] | [0.0, 6.0] |

## 拓扑 7 / 12 Integrator

12 Integrator — 积分器 — 做到

固定Gate6V，多输入近间隔累计一次、远间隔不发，重复1/0/1/0；单输入0。 同拓扑历史RAW复用，采样仍10Ω。

Vin：`near_far_pulses`；Vgate：`constant`；分项：`sequence, near, far, single`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_seed_b12_w0.66 | [0.0, 5.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 07_seed_b12_final_single | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 7 / 13 Rebound spike

13 Rebound spike — 反弹单发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：四拓扑统一：0→−5 V→0，恒Gate=6 V；在负脉冲撤去后检验单发与簇发，没有重新施加正Vin。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 07_negative_b6_n-5_g6 | [-5.0, 6.0] | [0.0, 6.0] |
| 2 | 灰实线 · 对照 07_rebound_bias_only | [0.0, 6.0] | [0.0, 6.0] |

## 拓扑 7 / 14 Rebound burst

14 Rebound burst — 反弹簇发 — 未做到

负Vin撤去后返回0、Gate恒定；当前测试未得到目标反弹发放。此前返回正偏置的曲线仅保留作历史对照。 展示激励：与13使用同一负输入撤去测试；检查释放后是否形成有限脉冲簇。

Vin：`negative_release`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_atlas_m13_0 | [-5.0, 0.0] | [0.0, 6.0] |

## 拓扑 7 / 15 Threshold variability

15 Threshold variability — 阈值可变性 — 做到

同幅Vin配合不同高度、对齐的长Gate方波，分别不发、少发、多发。 无Gate记忆电容。

Vin：`positive_window`；Vgate：`three_gate_levels`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular15 | [0.0, 4.0] | [0.0, 6.0] |

## 拓扑 7 / 16 Bistability

16 Bistability — 双稳态 — 做到*

Gate先恒定，Vin方波启动发放；Vin仍高时一个正向Gate方波停止重复尖峰。停止段进入低阻直流，不代表电流归零；不宣称同偏置双吸引子。⑦最终Vin=4.4 V、Gate=6→12 V，步长减半均为19次后停止。

Vin：`positive_window`；Vgate：`stop_gate_step`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_final16_v4.4 | [0.0, 4.4] | [0.0, 12.0] |

## 拓扑 7 / 17 Depolarizing after-potential

17 Depolarizing after-potential — 去极化后电位 — 未做到

原负电流瞬态不能证明去极化后电位，当前源极采样也不能读取全部Mott负瞬态；该功能未验证。

Vin：`positive_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_negative_output_step0.00025 | [0.0, 4.0] | [0.0, 2.0] |
| 1 | 橙实线 · 对照 07_regular17_g2 | [0.0, 4.0] | [0.0, 2.0] |
| 2 | 灰实线 · 对照 07_negative_output_step0.0005 | [0.0, 4.0] | [0.0, 2.0] |

## 拓扑 7 / 18 Accommodation

18 Accommodation — 适应性 — 未做到

恒Gate快慢输入均会发放，原窗口关闭形成的选择不足以证明适应性；本次不支持。

Vin：`fast_slow_ramp`；Vgate：`constant_or_window`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_final18_window_rise0.02 | [0.0, 5.0] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 07_final18_window_rise80 | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 7 / 19 Inhibition-induced spiking

19 Inhibition-induced spiking — 抑制诱导发放 — 做到*

Vin=−5 V、Gate=6 V、RLIMIT=3.3 kΩ，两个60 μs窗各18次反向发放。改的是现有限流电阻，采样仍10Ω。

Vin：`negative_window`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_negative_tonic_r3300_v-5 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 07_final19_zero_control | [0.0, 0.0] | [0.0, 6.0] |

## 拓扑 7 / 20 Inhibition-induced bursting

20 Inhibition-induced bursting — 抑制诱导簇发 — 做到*

每个长窗三段−5 V输入、Gate恒压6 V，形成三组反向发放；RLIMIT=3.3 kΩ。Gate=0时仍可反向发放，说明体二极管通路限制负向关断，不能当作理想抑制使能。

Vin：`negative_bursts`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_final20_negative_g6 | [-5.0, 0.0] | [0.0, 6.0] |
| 1 | 橙实线 · 对照 07_final20_negative_g0 | [-5.0, 0.0] | [0.0, 0.0] |
| 2 | 灰实线 · 对照 07_final19_zero_control | [0.0, 0.0] | [0.0, 6.0] |

## 拓扑 7 / 21 All-or-none response

21 All-or-none response — 全或无响应 — 做到

恒定Gate，不同幅度Vin展示不发与发放；采用较低后续电流的工作点，不把脉冲间的低电流中位数当静态电流。

Vin：`multi_level_pulses`；Vgate：`constant`；分项：`sequence, low, mid, high`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular21_g4 | [0.0, 5.0] | [0.0, 4.0] |

## 拓扑 7 / 22 Refractory period

22 Refractory period — 不应期 — 做到*

Gate恒压；单个探针各自能触发，短间隔对只产生一次Mott开关、稍长间隔产生两次。附局部放大。仅证明未复位电流合并与恢复，不宣称严格绝对不应期；间隔从下降沿起点计，含20 ns下降时间。

Vin：`paired_probes`；Vgate：`constant`；分项：`pair, first, second`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_verify_seed_b22_gap0.05 | [0.0, 5.0] | [0.0, 6.0] |
| 1 | 橙实线 · 主例 07_verify_seed_b22_gap0.1 | [0.0, 5.0] | [0.0, 6.0] |
| 2 | 灰实线 · 对照 07_final22_single1 | [0.0, 5.0] | [0.0, 6.0] |
| 3 | 紫实线 · 对照 07_final22_single2 | [0.0, 5.0] | [0.0, 6.0] |

## 拓扑 7 / 23 Depolarization block

23 Depolarization block — 去极化阻滞 — 做到

恒定Gate，Vin上升—平台—归零。上升途中发放，强输入段转为连续低阻导通；阻断的是重复尖峰而不是直流。

Vin：`ramp_hold`；Vgate：`constant`；分项：`default`。

| variant | 实验 / 对照 | Vin / V | Vgate / V |
|---:|---|---|---|
| 0 | 蓝实线 · 主例 07_regular23 | [0.0, 8.0] | [0.0, 6.0] |
