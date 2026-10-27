"""Four-channel Vin/Vgate scenes for AD9106 SRAM or FPGA events/native DDS."""
import argparse
import csv
import json
import math
import struct
import sys
from fractions import Fraction
from functools import reduce
from operator import xor
from pathlib import Path

from ad9106_uart import decode_reply, STATUS
from firing_waveforms import make_waveform, select_entry, absolute_levels, binding_frequency, align_resonator_gate, binding_phase, binding_time_offset

ROOT=Path(__file__).resolve().parents[1]
HARDWARE_PATTERN_REPEATS=2
STATUS[8]="scene session conflict (legacy presets require reset after scene mode)"


def lcm(a,b): return a*b//math.gcd(a,b)


def frame(seq,cmd,payload=b""):
    if len(payload)>18: raise ValueError("Scene payload exceeds 18 bytes")
    packet=bytearray([0xaa,0x55,seq&255,cmd])+bytearray(payload.ljust(18,b"\x00"))
    packet+=bytes([reduce(xor,packet[2:],0),13])
    return bytes(packet)


def encode_words(words):
    """BEGIN, contiguous 1..7-word blocks, COMMIT. Returns all bytes and SPI oracle."""
    packets=[frame(0,0x40)]
    index=0
    while index<len(words):
        address=words[index][0]; values=[words[index][1]]
        while index+len(values)<len(words) and len(values)<7:
            next_addr,next_value=words[index+len(values)]
            if next_addr!=address+len(values): break
            values.append(next_value)
        payload=struct.pack(">HB",address,len(values))+b"".join(struct.pack(">H",v) for v in values)
        packets.append(frame(len(packets),0x41,payload)); index+=len(values)
    packets.append(frame(len(packets),0x42))
    begin=[(0x1e,0)]+[(a,0) for a in range(0x32,0x36)]+[(a,0) for a in range(0x22,0x26)]+[(0x1d,1)]
    # Rev.C p31: configure, set RUN, write RAMUPDATE, then lower TRIGGER.
    # COMMIT reasserts finite playback even if a prior scene used continuous mode.
    commit=[(0x1e,1),(0x1d,1)]
    return packets,begin+words+commit


def voltage_code(value,full_scale,zero):
    if not math.isfinite(value): raise ValueError("Nonfinite output voltage")
    if abs(value)>10+1e-10: raise ValueError("Requested voltage exceeds the backend's +/-10 V range")
    number=round((value-zero)*2048/full_scale)
    # Positive endpoint is one LSB below +full_scale in a signed 12-bit DAC.
    if number==2048 and value<=zero+full_scale+1e-10: number=2047
    if not -2048<=number<=2047: raise ValueError("Requested voltage exceeds configured bipolar output range")
    return number


def common_frequency(frequencies):
    denominator=reduce(lcm,[f.denominator for f in frequencies],1)
    numerator=reduce(math.gcd,[f.numerator*(denominator//f.denominator) for f in frequencies])
    return Fraction(numerator,denominator)


def sample_wave(wave,n,cycles,phase,scale,offset,full_scale,zero,sample_count=None,strict=False):
    if wave.points:
        for a,b in zip(wave.points,wave.points[1:]):
            width=(b[0]-a[0])/wave.period_us*n/cycles
            if (strict or a[1]==b[1]) and 0 < width < 1-1e-9:
                raise ValueError("无法保留短平台或间隙：该段不足一个 DAC 采样间隔；不会自动拉宽或合并脉冲")
    values=[voltage_code(wave.value(i*cycles/n+phase)*scale+offset,full_scale,zero)
            for i in range(n if sample_count is None else sample_count)]
    return values,0


def zero_tail_length(wave,n,cycles,phase,scale,offset,zero):
    """Prove a PWL suffix is exactly the DAC idle code before omitting it.

    Keep the entire prefix, including all leading zeros and internal gaps.
    Phase-shifted and analytic waves deliberately use only the original path.
    """
    if not wave.points or wave.analytic or phase%1 != 0:
        raise ValueError("末尾等待优化仅适用于无循环时间偏移且末尾回到零码的分段波形")
    if any(abs(v*scale+offset-zero)>1e-12 for _,v in wave.points[-1:]):
        raise ValueError("波形末尾不是零码，不能用芯片空闲段代替")
    last=0
    for a,b in zip(wave.points,wave.points[1:]):
        if abs(a[1]*scale+offset-zero)>1e-12 or abs(b[1]*scale+offset-zero)>1e-12:
            last=max(last,b[0])
    if last>=wave.period_us:
        raise ValueError("波形没有可省略的末尾零码等待段")
    return min(n,max(1,math.ceil((cycles-1+last/wave.period_us)*n/cycles)+1))


def compile_scene(config,catalog,_compact=False,_capacity_failures=None,_waveforms=None):
    if config.get("static_pulse"):
        from static_pulse import compile_static_pulse
        return compile_static_pulse(config,catalog)
    if any(b.get("enabled",True) and int(b.get("mode",0)) in (25,26) for b in config.get("channels",[])):
        from basic_waveforms import compile_basic_scene
        return compile_basic_scene(config,catalog)
    dac_clock=float(config.get("dac_clock_hz",148500000))
    full_scale=float(config.get("full_scale_v",10)); zero=float(config.get("zero_code_v",0))
    max_ppm=float(config.get("max_frequency_error_ppm",1000))
    if not all(math.isfinite(x) for x in (dac_clock,full_scale,zero,max_ppm)) or dac_clock<=0 or full_scale<=0 or full_scale>10 or max_ppm<0:
        raise ValueError("Invalid DAC clock, output calibration or frequency tolerance")
    prepared=[]; pairs={}; used=set()
    for binding in config.get("channels",[]):
        channel=int(binding["channel"])
        if channel not in (1,2,3,4) or channel in used: raise ValueError("channel must be unique and in 1..4")
        used.add(channel)
        if not binding.get("enabled",True): continue
        if _waveforms is not None and channel in _waveforms:
            entry,case=select_entry(catalog,int(binding["topology"]),int(binding["mode"]),binding.get("variant",0))
            wave=_waveforms[channel]
        else: wave,entry,case=make_waveform(catalog,binding)
        frequency=binding_frequency(binding) if wave.constant is None else Fraction(100000)
        if int(binding["mode"])==24 and wave.constant is None:
            period=Fraction(str(binding.get("parameters",{}).get("period_us",100)))
            if abs(float(frequency*period)-1000000)>0.001:
                raise ValueError("静态扫描时窗时长必须与 period_us 一致，以保持脉宽准确")
        reference_peak=max(abs(v) for v in case[binding["signal"]+"_range_v"])
        amplitude=float(binding.get("amplitude_v",min(full_scale,reference_peak)))
        offset=float(binding.get("offset_v",0)); phase=binding_phase(binding,frequency) if wave.constant is None else 0
        if not all(math.isfinite(x) for x in (amplitude,offset,phase)) or amplitude<0:
            raise ValueError("Invalid amplitude/offset/phase")
        scale=1 if absolute_levels(binding) else amplitude/reference_peak if reference_peak else 0
        row={"channel":channel,"wave":wave,"entry":entry,"case":case,"binding":binding,
             "frequency":frequency,"scale":scale,"offset":offset,"phase":phase,
             "time_offset_us":binding_time_offset(binding,frequency) if wave.constant is None else 0,
             "amplitude_v":amplitude,"reference_peak_v":reference_peak}
        prepared.append(row)
        if binding.get("pair"): pairs.setdefault(str(binding["pair"]),[]).append(row)
    for name,rows in pairs.items():
        if len(rows)!=2 or {r["binding"]["signal"] for r in rows}!={"vin","gate"}:
            raise ValueError("配对 {} 未配对成功：需要恰好一条启用的 Vin 和一条启用的 Vgate；单路测试请将配对设为“无”".format(name))
        keys=("topology","mode","variant","component")
        for key in keys:
            default={"variant":0,"component":rows[0]["entry"]["components"][0],"parameters":{},"phase_deg":0}.get(key)
            if rows[0]["binding"].get(key,default)!=rows[1]["binding"].get(key,default):
                label={"topology":"拓扑","mode":"模式","variant":"实验变体","component":"序列分段","phase_deg":"相位","parameters":"时序参数"}[key]
                raise ValueError("配对 {} 的两路{}不一致，请同步配对设置".format(name,label))
        if int(rows[0]["binding"]["mode"])==11:
            vin=next(r for r in rows if r["binding"]["signal"]=="vin")
            gate=next(r for r in rows if r["binding"]["signal"]=="gate")
            align_resonator_gate(vin["wave"],gate["wave"],vin["frequency"],gate["frequency"],gate["case"]["gate_range_v"][1])
    active=[r for r in prepared if r["wave"].constant is None and r["scale"]!=0]
    static_active=[r for r in active if int(r["binding"]["mode"])==24]
    if static_active and (len(static_active)!=len(active) or len({r["frequency"] for r in static_active})!=1):
        raise ValueError("静态扫描只能与相同时窗的静态扫描通道一起发送，防止一个触发中重复产生 Vin 脉冲")
    base=common_frequency([r["frequency"] for r in active]) if active else Fraction(100000)
    minimum_multiple=1
    for row in active:
        ratio=row["frequency"]/base
        # Continuous sine Gate may need several Vin envelope periods per SRAM frame.
        minimum_multiple=lcm(minimum_multiple,row["wave"].continuity_multiple//math.gcd(ratio.numerator,row["wave"].continuity_multiple))
    ideal=Fraction(str(dac_clock))/base*minimum_multiple
    multipliers={minimum_multiple}
    if ideal.denominator<=64: multipliers.add(minimum_multiple*ideal.denominator)
    candidates=[]; failures=[]; capacity_failures=list(_capacity_failures or [])
    for multiple in sorted(multipliers):
        target_ticks=dac_clock/float(base)*multiple
        for hold in range(1,17):
            timings=[]
            for period_base in range(1,17):
                quantum=lcm(hold,period_base)
                ticks=int(math.floor(target_ticks/quantum+.5))*quantum
                if ticks<hold or ticks//period_base>65535: continue
                error=abs(target_ticks/ticks-1)
                timings.append((error,ticks,period_base))
            if not timings: continue
            error,ticks,period_base=min(timings)
            n=ticks//hold
            if active and ((n>4096 and not _compact) or n<32*max(int(r["frequency"]/base)*multiple for r in active)): continue
            if any(r["wave"].sine_period_us and n < 8*int(r["frequency"]/base)*multiple*r["wave"].period_us/r["wave"].sine_period_us for r in active):
                continue
            if error*1e6>max_ppm: continue
            memory=[]; allocations={}; channels=[]
            try:
                for channel in range(1,5):
                    row=next((r for r in prepared if r["channel"]==channel),None)
                    if row is None:
                        channels.append({"channel":channel,"source":"constant","constant_code":0,"frequency_hz":0})
                        continue
                    wave=row["wave"]; cycles=int(row["frequency"]/base)*multiple if wave.constant is None else 0
                    phase=(-row["time_offset_us"]*cycles*dac_clock/ticks/1e6
                           if "time_offset_us" in row["binding"] else row["phase"])
                    if wave.constant is not None or row["scale"]==0:
                        value=(wave.constant or 0)*row["scale"]+row["offset"]
                        codes=[voltage_code(value,full_scale,zero)]; snaps=0
                    else:
                        count=n
                        if _compact:
                            try:
                                count=zero_tail_length(wave,n,cycles,phase,row["scale"],row["offset"],zero)
                            except ValueError:
                                if n>4096: raise
                            if count>4096:
                                raise ValueError("有效波形及内部间隙需要 {} 点，超过共享 4096 点容量，不能保留细节".format(count))
                        codes,snaps=sample_wave(wave,n,cycles,phase,row["scale"],row["offset"],full_scale,zero,
                                               sample_count=count)
                        if min(codes)==max(codes):
                            raise ValueError("动态波形在当前采样或电压精度下退化为直流，已拒绝；请调整时长或幅值")
                    is_dc=min(codes)==max(codes)
                    result={"channel":channel,"topology":row["entry"]["topology"],"mode":row["entry"]["mode"],
                            "variant":row["case"]["variant"],"experiment":row["case"]["experiment"],
                            "signal":row["binding"]["signal"],"component":row["binding"].get("component",row["entry"]["components"][0]),
                            "requested_frequency_hz":float(row["frequency"]),"frequency_hz":0 if is_dc else cycles*dac_clock/ticks,
                            "cycles_per_frame":0 if is_dc else cycles,"amplitude_v":row["amplitude_v"],
                            "time_offset_us":row["time_offset_us"],
                            "reference_peak_v":row["reference_peak_v"],"min_code":min(codes),"max_code":max(codes),
                            "nominal_min_v":zero+min(codes)*full_scale/2048,"nominal_max_v":zero+max(codes)*full_scale/2048,
                            "snapped_short_plateaus":snaps,"reference_period_us":wave.period_us,
                            "time_resolution_ns":hold/dac_clock*1e9,"source":"constant" if is_dc else "sram"}
                    if wave.sine_period_us and not is_dc:
                        result["sine_carrier_hz"]=result["frequency_hz"]*wave.period_us/wave.sine_period_us
                    if is_dc: result["constant_code"]=codes[0]
                    else:
                        key=tuple(codes)
                        if key not in allocations:
                            allocations[key]=len(memory); memory.extend(codes)
                        result.update(start=allocations[key],stop=allocations[key]+len(codes)-1,samples=codes,
                                      zero_tail_samples=n-len(codes))
                    channels.append(result)
                if len(memory)>4096:
                    capacity_failures.append((len(memory),hold,
                        "、".join("DAC{} {} 点".format(c["channel"],len(c["samples"]))
                                  for c in channels if c["source"]=="sram")))
                    continue
            except ValueError as ex:
                failures.append("HOLD={}（采样间隔 {:.6g} μs）时，DAC{}：{}".format(
                    hold,hold/dac_clock*1e6,channel,ex)); continue
            score=(round(error,12),hold,len(memory),multiple)
            candidates.append((score,dict(dac_clock_hz=dac_clock,full_scale_v=full_scale,zero_code_v=zero,
                frame_frequency_hz=dac_clock/ticks,pattern_ticks=ticks,pattern_period=ticks//period_base,
                period_base=period_base,hold=hold,samples_per_frame=n,sram_words=len(memory),
                frequency_error_ppm=error*1e6,channels=channels,memory=memory)))
    if not candidates:
        if not _compact:
            return compile_scene(config,catalog,_compact=True,_capacity_failures=capacity_failures,_waveforms=_waveforms)
        if capacity_failures:
            words,hold,usage=min(capacity_failures)
            detail="；已检查方案中占用最少的可采样方案：HOLD={}，{}，去重后合计 {} 点，超出 {} 点".format(
                hold,usage,words,words-4096)
            if failures: detail+="；其他采样方案仍有约束，例如："+failures[-1]
        else:
            detail=("；"+failures[-1]) if failures else "；未找到同时满足公共播放周期、采样点数和计时误差的方案"
        raise ValueError("当前场景超出 AD9106 共享 4096 点存储 / HOLD 1..16 / 公共时窗及计时误差限制"+detail+
                         "。无法在当前时长保留波形细节，未发送配置。请按上述原因调整有效时长、脉冲数量或过短的边沿；不会自动删点、拉宽脉冲或更改其他通道时长。")
    plan=min(candidates,key=lambda c:c[0])[1]
    # Report actual allocation, rather than implying that each DAC owns 1024/2048 words.
    plan["sample_interval_us"]=plan["hold"]/dac_clock*1e6
    plan["sram_free_words"]=4096-plan["sram_words"]
    for c in plan["channels"]:
        c["sram_words"]=len(c["samples"]) if c["source"]=="sram" else 0
        c["shared_with"]=[other["channel"] for other in plan["channels"]
            if c["source"]==other["source"]=="sram" and other["channel"]!=c["channel"]
            and (c["start"],c["stop"])==(other["start"],other["stop"])]
        c["sampling_warnings"]=[]
        row=next((r for r in prepared if r["channel"]==c["channel"]),None)
        if c["source"]=="sram" and row and row["wave"].points:
            segments=[b[0]-a[0] for a,b in zip(row["wave"].points,row["wave"].points[1:]) if b[0]>a[0]]
            if segments:
                shortest=min(segments)/row["wave"].period_us/c["frequency_hz"]*1e6
                c["shortest_segment_us"]=shortest
                if shortest < plan["sample_interval_us"]*(1-1e-9):
                    c["sampling_warnings"].append("最短边沿或平台 {:.6g} μs 小于采样间隔 {:.6g} μs，无法精确还原该段".format(
                        shortest,plan["sample_interval_us"]))
    plan["storage_mode"]="zero_tail" if _compact else "full_frame"
    # Each trigger plays two SRAM units; the chip ends the finite burst.
    plan["pattern_duration_us"]=plan["pattern_ticks"]/plan["dac_clock_hz"]*1e6
    plan["hardware_pattern_repeats"]=HARDWARE_PATTERN_REPEATS
    plan["burst_duration_us"]=plan["pattern_duration_us"]*HARDWARE_PATTERN_REPEATS
    # Each 8-bit DACx_REPEAT_CYCLE field stores the pattern count minus one.
    repeat_word=(HARDWARE_PATTERN_REPEATS-1)*0x0101
    words=[(0x1f,1),(0x20,14),(0x44,0),(0x45,0),(0x1e,4)]
    words.extend((0x6000+i,(v&4095)<<4) for i,v in enumerate(plan["memory"]))
    words.append((0x1e,0))
    hold=plan["hold"]%16; period_base=plan["period_base"]%16
    words.extend([(0x28,(hold<<8)|(period_base<<4)|hold),(0x29,plan["pattern_period"]),
                  (0x2a,repeat_word),(0x2b,repeat_word)])
    source_bytes={c["channel"]:(1 if c["source"]=="constant" else 0) for c in plan["channels"]}
    words.extend([(0x26,(source_bytes[4]<<8)|source_bytes[3]),(0x27,(source_bytes[2]<<8)|source_bytes[1])])
    for c in plan["channels"]:
        ch=c["channel"]; delay_reg=0x5c-4*(ch-1)
        words.extend([(0x36-ch,0x4000),(0x26-ch,0),
                      (0x32-ch,(c.get("constant_code",0)&4095)<<4),
                      (delay_reg,0),(delay_reg+1,c.get("start",0)<<4),(delay_reg+2,c.get("stop",0)<<4)])
    packets,oracle=encode_words(words)
    plan["register_and_sram_writes"]=words; plan["spi_oracle"]=oracle
    plan["packets"]=[p.hex(" ").upper() for p in packets]
    plan["notes"]=["Nominal bipolar voltage calibration; verify actual DAC+amplifier transfer before voltage-critical use.",
                   "Graph/text-derived templates; time/voltage quantization can change neuron responses.",
                   "All channels restart together; different frequencies use a common superperiod, not independent hardware clocks.",
                   "frequency_hz denotes template envelope repetition; continuous sine Gate carrier is reported separately."]
    return plan


def export_plan(plan,directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    (directory/"plan.json").write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding="utf-8")
    packets=[bytes.fromhex(p) for p in plan["packets"]]
    (directory/"packets.bin").write_bytes(b"".join(packets))
    (directory/"frames.mem").write_text("\n".join("{:02x}".format(b) for p in packets for b in p)+"\n",encoding="ascii")
    (directory/"expected_spi.mem").write_text("\n".join("{:08x}".format((a<<16)|v) for a,v in plan["spi_oracle"])+"\n",encoding="ascii")
    (directory/"counts.txt").write_text("{} {} {}\n".format(len(packets),len(plan["spi_oracle"]),math.ceil(plan["pattern_ticks"]*100000000/plan["dac_clock_hz"])+100),encoding="ascii")
    for channel in plan["channels"]:
        with (directory/("dac{}.csv".format(channel["channel"]))).open("w",newline="",encoding="utf-8") as stream:
            writer=csv.writer(stream); writer.writerow(["sample","time_us","code","nominal_volts"])
            codes=channel.get("samples",[channel.get("constant_code",0)])
            for i,code in enumerate(codes):
                time_us=channel["sample_times_us"][i] if "sample_times_us" in channel else i*channel.get("preview_step_us",plan["hold"]/plan["dac_clock_hz"]*1e6)
                writer.writerow([i,time_us,code,plan["zero_code_v"]+code*plan["full_scale_v"]/2048])
            if channel.get("zero_tail_samples",0):
                for i in sorted({len(codes),plan["samples_per_frame"]-1}):
                    writer.writerow([i,i*plan["hold"]/plan["dac_clock_hz"]*1e6,0,plan["zero_code_v"]])


def send_plan(plan,port_name,baud=115200,progress=None):
    try: import serial
    except ImportError: raise ValueError("Sending requires pyserial: python -m pip install pyserial")
    packets=[bytes.fromhex(p) for p in plan["packets"]]
    with serial.Serial(port_name,baud,timeout=2,bytesize=8,parity="N",stopbits=1) as port:
        port.reset_input_buffer(); begun=False
        try:
            for index,packet in enumerate(packets):
                port.write(packet); port.flush()
                status=decode_reply(port.read(8),packet[2],packet[3])
                if status: raise ValueError(STATUS.get(status,"unknown status"))
                begun=True
                if progress: progress(index+1,len(packets))
                if index%50==0 or index==len(packets)-1: print("ACK {}/{}".format(index+1,len(packets)))
        except Exception:
            if begun:
                try:
                    port.write(frame((packet[2]+1)&255,0x43)); port.flush(); port.read(8)
                except Exception: pass
            raise


def send_abort(port_name,baud=115200):
    try: import serial
    except ImportError: raise ValueError("Sending requires pyserial: python -m pip install pyserial")
    packet=frame(0,0x43)
    with serial.Serial(port_name,baud,timeout=2,bytesize=8,parity="N",stopbits=1) as port:
        port.reset_input_buffer(); port.write(packet); port.flush()
        status=decode_reply(port.read(8),0,0x43)
        if status: raise ValueError(STATUS.get(status,"unknown status"))
    print("ABORT acknowledged; all four digital outputs muted.")


def send_retrigger(port_name,baud=115200):
    """Rearm RUN and replay the committed pattern without rewriting SRAM."""
    try: import serial
    except ImportError: raise ValueError("Sending requires pyserial: python -m pip install pyserial")
    packet=frame(0,0x44)
    with serial.Serial(port_name,baud,timeout=2,bytesize=8,parity="N",stopbits=1) as port:
        port.reset_input_buffer(); port.write(packet); port.flush()
        status=decode_reply(port.read(8),0,0x44)
        if status: raise ValueError(STATUS.get(status,"unknown status"))


def report(plan):
    print("Common frame {:.9f} us; HOLD={}; SRAM={}/4096".format(
        plan["pattern_duration_us"],plan["hold"],plan["sram_words"]))
    for c in plan["channels"]:
        duration="{:.9f} us".format(1e6/c["frequency_hz"]) if c.get("frequency_hz") else "DC"
        if c.get("source")=="dds": duration="{:.9f} Hz".format(c["frequency_hz"])
        print("DAC{} {}: {}; codes {}..{}{}".format(c["channel"],c["source"],duration,
            c.get("min_code",c.get("constant_code",0)),c.get("max_code",c.get("constant_code",0)),
            "; short plateaus snapped={}".format(c.get("snapped_short_plateaus",0))))
        if c.get("reference_peak_v",0)>plan["full_scale_v"]: print("  Reference peak exceeds output range; selected amplitude was scaled explicitly in this plan.")
        if "sine_carrier_hz" in c: print("  Sine Gate frequency: {:.9f} Hz".format(c["sine_carrier_hz"]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    listing=sub.add_parser("catalog"); listing.add_argument("--topology",type=int); listing.add_argument("--mode",type=int)
    abort=sub.add_parser("abort"); abort.add_argument("--port",required=True); abort.add_argument("--baud",type=int,default=115200)
    for command in ("program","set"):
        p=sub.add_parser(command)
        p.add_argument("--scene",type=Path,default=ROOT/".uart_sim/firing_scene.json")
        p.add_argument("--out",type=Path,default=ROOT/".uart_sim/firing_plan")
        p.add_argument("--port"); p.add_argument("--baud",type=int,default=115200)
        if command=="set":
            p.add_argument("--channel",type=int,required=True); p.add_argument("--topology",type=int,required=True)
            p.add_argument("--mode",type=int,required=True); p.add_argument("--variant",default="0")
            p.add_argument("--signal",choices=["vin","gate"],required=True); p.add_argument("--component")
            timing=p.add_mutually_exclusive_group(required=True)
            timing.add_argument("--duration-us",type=float,help="整组时窗 / 标准波形单周期时长，单位 μs")
            timing.add_argument("--frequency",type=float,help="正弦频率，单位 Hz；也兼容旧版波形频率输入")
            p.add_argument("--amplitude",type=float)
            p.add_argument("--offset",type=float,default=0)
            shift=p.add_mutually_exclusive_group()
            shift.add_argument("--time-offset-us",type=float,help="循环时间偏移：正数延后，负数提前，单位 μs")
            shift.add_argument("--phase",type=float,help=argparse.SUPPRESS)
    args=parser.parse_args()
    from firing_gui_core import load_catalog
    catalog=load_catalog()
    try:
        if args.command=="abort":
            send_abort(args.port,args.baud); return
        if args.command=="catalog":
            for entry in catalog["modes"]:
                if args.topology and entry["topology"]!=args.topology: continue
                if args.mode and entry["mode"]!=args.mode: continue
                print("T{} {:02d} {} components={}".format(entry["topology"],entry["mode"],entry["name"],entry["components"]))
                for case in entry["cases"]: print("  {} {} Vin={} Gate={}".format(case["variant"],case["experiment"],case["vin_range_v"],case["gate_range_v"]))
            return
        if args.scene.exists(): config=json.loads(args.scene.read_text(encoding="utf-8"))
        elif args.command=="set": config={"channels":[],"full_scale_v":10}
        else: raise ValueError("Scene JSON does not exist")
        if args.command=="set":
            old=next((b for b in config.get("channels",[]) if b["channel"]==args.channel),{})
            if old.get("pair"):
                for member in config.get("channels",[]):
                    if member.get("pair")==old["pair"]: member.pop("pair",None)
            binding=dict(channel=args.channel,topology=args.topology,mode=args.mode,variant=args.variant,
                         signal=args.signal,offset_v=args.offset)
            if args.phase is not None: binding["phase_deg"]=args.phase
            else: binding["time_offset_us"]=args.time_offset_us or 0
            if args.duration_us is not None: binding["duration_us"]=args.duration_us
            else: binding["frequency_hz"]=args.frequency
            if args.amplitude is not None: binding["amplitude_v"]=args.amplitude
            if args.component: binding["component"]=args.component
            config["channels"]=[b for b in config.get("channels",[]) if b["channel"]!=args.channel]+[binding]
        plan=compile_scene(config,catalog); export_plan(plan,args.out); report(plan)
        if args.port: send_plan(plan,args.port,args.baud)
        if args.command=="set":
            args.scene.parent.mkdir(parents=True,exist_ok=True)
            args.scene.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Sent and started synchronously." if args.port else "Plan only; nothing sent to hardware.")
    except (ValueError,KeyError,OverflowError,OSError) as error: parser.error(str(error))


if __name__=="__main__":
    main()
