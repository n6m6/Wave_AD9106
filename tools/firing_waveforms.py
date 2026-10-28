"""Graph/text-derived Vin and Vgate templates, expressed in reference us/V.

The HTML supplies voltage ranges and some timing, not original stimulus files.
Every template is editable PWL/analytic data; unsupported neuron responses remain
selectable INPUT stimuli and are never relabelled as successful neuron modes.
"""
import bisect
import math
import re
from fractions import Fraction


PERIOD_US = {1:160,2:160,3:220,4:220,5:220,6:220,7:200,8:350,9:100,
             10:220,11:150,12:180,13:160,14:160,15:180,16:220,17:110,
             18:200,19:100,20:220,21:180,22:35,23:220}

LEVEL_KEYS = ("level_low_v", "level_mid_v", "level_high_v")
EXTRA_PARAMETERS = {"vin_width_us", "gate_width_us", "pulse_gap_us", "vin_frequency_khz",
                    "rise_time_us", "fall_time_us",
                    "vin_duty_percent", "gate_frequency_khz", "vin_period_us", "gate_period_us", "first_stage_us", "second_stage_us",
                    "stage1_voltage_v", "stage2_voltage_v", *LEVEL_KEYS}


def edge_time_parameters(parameters):
    """Validate physical edge times while preserving legacy reference fields."""
    result={}
    for key in ("rise_time_us","fall_time_us"):
        if key not in parameters:continue
        try:
            value=float(parameters[key])
            if isinstance(parameters[key],bool) or not math.isfinite(value) or not 0<=value<=1:
                raise ValueError()
        except (ValueError,TypeError,OverflowError):
            raise ValueError("上升时间和下降时间必须是 0～1 μs 的有限数值") from None
        result[key]=value
    return result


def positive_time(value, label):
    """Keep decimal times rational, including reciprocals imported from old scenes."""
    try:
        number=float(value)
        if isinstance(value,bool) or not math.isfinite(number) or number<=0: raise ValueError()
        result=Fraction(str(value)).limit_denominator(1000000000)
        if result<=0: raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        raise ValueError(label+"必须是大于 0 的有限数值") from None


def binding_frequency(binding, default=None):
    """Compiler-only frequency; new scenes store the actual duration in microseconds."""
    if "duration_us" in binding:
        frequency=1000000/positive_time(binding["duration_us"],"时窗 / 单周期时长")
        if "frequency_hz" in binding and not math.isclose(float(binding["frequency_hz"]),float(frequency),rel_tol=1e-12):
            raise ValueError("时长与旧版频率字段不一致，请仅保留 duration_us")
        return frequency
    value=binding.get("frequency_hz",default)
    if value is None: raise ValueError("缺少时窗 / 单周期时长 duration_us")
    try:
        frequency=Fraction(str(value))
        if frequency<=0: raise ValueError()
        return frequency
    except (ValueError, TypeError, ZeroDivisionError):
        raise ValueError("时窗 / 单周期时长必须是大于 0 的有限数值") from None


def absolute_levels(binding):
    """The three individually entered voltages are output targets, not ratios."""
    mode=int(binding["mode"]); signal=binding["signal"]; params=binding.get("parameters",{})
    if (mode,signal) in ((15,"gate"),(21,"vin")):
        return any(key in params for key in LEVEL_KEYS)
    if (mode,signal) in ((5,"gate"),(7,"vin")):
        return any(key in params for key in ("stage1_voltage_v","stage2_voltage_v","gate_initial_v","gate_final_v"))
    return mode==6 and signal=="gate" and any(key in params for key in ("gate_initial_v","gate_final_v"))


def binding_time_offset(binding,frequency=None):
    """Positive microseconds delay the periodic waveform; old angles advanced it."""
    frequency=float(binding_frequency(binding) if frequency is None else frequency)
    def finite(value):
        try:
            result=float(value)
            if isinstance(value,bool) or not math.isfinite(result): raise ValueError()
            return result
        except (ValueError,TypeError,OverflowError):
            raise ValueError("时间偏移必须是有限数值（正数延后，负数提前）") from None
    old=-finite(binding.get("phase_deg",0))/360/frequency*1e6
    if "time_offset_us" not in binding: return old
    value=finite(binding["time_offset_us"])
    if "phase_deg" in binding and not math.isclose(value,old,rel_tol=1e-12,abs_tol=1e-10):
        raise ValueError("时间偏移与旧相位字段不一致，请仅保留 time_offset_us")
    return value


def binding_phase(binding,frequency=None):
    frequency=float(binding_frequency(binding) if frequency is None else frequency)
    offset=binding_time_offset(binding,frequency)
    return -offset*frequency/1e6 if "time_offset_us" in binding else float(binding.get("phase_deg",0))/360


def constant_output(topology,mode,signal,case):
    """Semantic DC channels, independent of leftover timing fields in old scenes."""
    if mode>24: return False
    if case[signal+"_range_v"]==[0,0]: return True
    if signal!="gate": return False
    if mode in (1,2,7,8,9,12,13,14,17,19,20,21,22,23,24): return True
    if mode==18 and topology==3: return True
    return mode==10 and "flat" in case.get("source_experiment",case["experiment"]).lower()


def align_resonator_gate(vin,gate,vin_frequency,gate_frequency,peak):
    """Anchor paired Gate to Vin in physical time, not copied template parameters."""
    if not gate.sine_period_us or len(vin.points)<5: return
    center=(vin.points[1][0]+vin.points[4][0])/2
    origin=center/vin.period_us/float(vin_frequency)*float(gate_frequency)*gate.period_us
    period=gate.sine_period_us
    gate.analytic=lambda t:peak*.5*(1+math.cos(2*math.pi*(t-origin)/period))


class Waveform:
    def __init__(self, period, points=None, analytic=None, constant=None, notes=None, sine_period=None):
        self.period_us = period
        self.points = sorted(points or [], key=lambda p:p[0])
        self.times = [p[0] for p in self.points]
        self.analytic = analytic
        self.constant = constant
        self.notes = notes or []
        self.sine_period_us = sine_period
        self.continuity_multiple = (Fraction(str(period))/Fraction(str(sine_period))).denominator if sine_period else 1
        if self.points and (self.points[0][0] < 0 or self.points[-1][0] > period+1e-8):
            raise ValueError("波形超出当前时窗：请缩短各段时间，或增大整组时窗时长")

    def value(self, phase):
        if self.constant is not None: return self.constant
        if self.analytic: return self.analytic(phase*self.period_us)
        t = (phase % 1.0) * self.period_us
        index = bisect.bisect_right(self.times, t)-1
        if index < 0: return self.points[0][1]
        if index >= len(self.points)-1: return self.points[-1][1]
        t0,v0 = self.points[index]; t1,v1 = self.points[index+1]
        return v0+(v1-v0)*(t-t0)/(t1-t0) if t1 != t0 else v1


def select_entry(catalog, topology, mode, variant=0):
    if mode in (27,28) and topology in (3,5,6,7):
        if str(variant)!="0":raise ValueError("节律调制只有一个实验变体")
        name="节律调制：Vin 方波 / Vgate 正弦" if mode==27 else "节律调制：Vin / Vgate 双方波"
        case={"variant":0,"experiment":"rhythm","vin_range_v":[-1,1],"gate_range_v":[-1,1]}
        return {"topology":topology,"mode":mode,"name":name,"description":name+"；频率和初始相位分别设置，观察窗结束归零。",
                "components":["rhythm"],"cases":[case]},case
    if mode in (25,26) and topology in (3,5,6,7):
        if str(variant)!="0": raise ValueError("Basic waveform has one variant")
        name="square" if mode==25 else "sine"
        case={"variant":0,"experiment":name,"vin_range_v":[-1,1],"gate_range_v":[-1,1]}
        return {"topology":topology,"mode":mode,"name":name,"components":[name],
                "description":"标准方波" if mode==25 else "芯片 DDS 正弦波","cases":[case]},case
    if mode == 24 and topology in (3,5,6,7):
        case={"variant":0,"experiment":"static_scan","vin_range_v":[0,1],"gate_range_v":[0,1]}
        if str(variant)!="0": raise ValueError("Static scan has one variant")
        return {"topology":topology,"mode":24,"components":["pulse"],
                "description":"Vgate 恒压，Vin 单个可调宽度方波。", "cases":[case]},case
    entry = next((e for e in catalog["modes"] if e["topology"]==topology and e["mode"]==mode), None)
    if entry is None: raise ValueError("topology must be 3/5/6/7 and mode must be 1..23")
    if isinstance(variant,str) and not variant.isdigit():
        matches = [c for c in entry["cases"] if c["experiment"]==variant]
        if not matches: raise ValueError("Unknown experiment variant: "+variant)
        case = matches[0]
    else:
        number=int(variant)
        if number < 0 or number >= len(entry["cases"]): raise ValueError("variant out of range")
        case=entry["cases"][number]
    return entry,case


def rhythm_square_value(cycles,frequency,duty,rise_us=0,fall_us=0):
    """A full-period square; ON time includes its linear rise and fall."""
    if rise_us==fall_us==0:return 1 if cycles%1<duty else -1
    t=(cycles%1)*1e6/frequency
    on_us=duty*1e6/frequency
    if t>=on_us:return -1
    if rise_us>0 and t<rise_us:return -1+2*t/rise_us
    fall_start=on_us-fall_us
    if math.isclose(rise_us+fall_us,on_us,rel_tol=1e-12,abs_tol=1e-12):fall_start=rise_us
    if fall_us>0 and t>fall_start:return 1-2*(t-fall_start)/fall_us
    return 1


def rhythm_binding(binding):
    """Translate an integrated rhythm mode into one sampled carrier."""
    mode=int(binding["mode"]);signal=binding.get("signal")
    if mode not in (27,28) or signal not in ("vin","gate"):
        raise ValueError("节律新模式需要 Vin / Vgate 信号")
    if str(binding.get("variant",0))!="0" or binding.get("component","rhythm")!="rhythm":
        raise ValueError("节律新模式只有默认变体和 rhythm 分段")
    p=binding.get("parameters",{})
    square=signal=="vin" or mode==28
    allowed={"rhythm_phase_deg","rhythm_duty_percent"} if square else {"rhythm_phase_deg"}
    if square:allowed.update(("rise_time_us","fall_time_us"))
    allowed.add("rhythm_on_us" if signal=="vin" else "rhythm_frequency_khz")
    if set(p)-allowed:raise ValueError("节律模式含有不适用的参数："+", ".join(sorted(set(p)-allowed)))
    try:
        duty=float(p.get("rhythm_duty_percent",50))
        if not math.isfinite(duty) or isinstance(p.get("rhythm_duty_percent"),bool) or not 0<duty<100:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValueError("方波占空比必须在 0～100% 之间") from None
    try:
        phase=float(p.get("rhythm_phase_deg",0))
        if not math.isfinite(phase) or isinstance(p.get("rhythm_phase_deg"),bool):raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValueError("初始相位必须是有限数值") from None
    if binding.get("time_offset_us",0) or binding.get("phase_deg",0):
        raise ValueError("节律新模式请使用本路初始相位 rhythm_phase_deg")
    frequency=(1000000*positive_time(duty/100,"占空比")/positive_time(p.get("rhythm_on_us",20),"Vin ON 时间")
               if signal=="vin" else 1000*positive_time(p.get("rhythm_frequency_khz",25),"Vgate 频率"))
    if square:
        edges=edge_time_parameters(p)
        if edges.get('rise_time_us',0)+edges.get('fall_time_us',0)>float(1000000/frequency)*duty/100+1e-9:
            raise ValueError("上升时间与下降时间之和不能超过方波 ON 时间；请缩短边沿或增大 ON 时间/占空比")
    result={k:v for k,v in binding.items() if k not in ("duration_us","frequency_hz","phase_deg","time_offset_us","parameters","component")}
    result.update(mode=25 if square else 26,frequency_hz=float(frequency),phase_deg=phase,
                  amplitude_v=binding.get("amplitude_v",.5),offset_v=binding.get("offset_v",.5),
                  parameters={"duty_percent":duty} if square else {})
    return result


def make_waveform(catalog, binding):
    topology=int(binding["topology"]); mode=int(binding["mode"])
    entry,case=select_entry(catalog,topology,mode,binding.get("variant",0))
    if mode in (27,28):
        standard=rhythm_binding(binding)
        window=float(positive_time(binding.get("duration_us",200),"节律观察时长"))
        frequency=float(binding_frequency(standard));phase=binding_phase(standard,frequency)%1
        duty=float(standard.get("parameters",{}).get("duty_percent",50))/100
        edges=edge_time_parameters(binding.get('parameters',{}))
        def value(t):
            if t>=window:return 0
            cycles=t*frequency/1e6+phase
            return math.sin(2*math.pi*(cycles%1)) if standard["mode"]==26 else rhythm_square_value(
                cycles,frequency,duty,edges.get('rise_time_us',0),edges.get('fall_time_us',0))
        return Waveform(window,analytic=value),entry,case
    if mode in (25,26):
        parameters=binding.get("parameters",{})
        if set(parameters)-({"duty_percent"} if mode==25 else set()):
            raise ValueError("标准波形仅方波支持 duty_percent；请清除旧模式的高级时序参数")
        if mode==26:
            return Waveform(1000,analytic=lambda t:math.sin(2*math.pi*t/1000)),entry,case
        duty=float(parameters.get("duty_percent",50))
        if not math.isfinite(duty) or not 0<duty<100: raise ValueError("方波占空比必须在 0～100% 之间")
        edge=10*duty
        return Waveform(1000,points=[(0,1),(edge,1),(edge,-1),(1000,-1)]),entry,case
    signal=binding["signal"].lower()
    if signal not in ("vin","gate"): raise ValueError("signal must be vin or gate")
    if constant_output(topology,mode,signal,case):
        return Waveform(PERIOD_US.get(mode,100),constant=case[signal+"_range_v"][1]),entry,case
    component=binding.get("component",entry["components"][0])
    if component not in entry["components"]: raise ValueError("Invalid component for this mode")
    parameters=binding.get("parameters",{})
    allowed={"period_us","start_us","width_us","rise_us","fall_us","ramp_us",
             "gap_us","pulse_period_us","pulse_count","gate_sine_period_us",
             "gate_floor_v","gate_initial_v","gate_final_v","gate_baseline_v","levels_v"} | EXTRA_PARAMETERS
    unknown=set(parameters)-allowed
    if unknown: raise ValueError("Unknown template parameters: "+", ".join(sorted(unknown)))
    actual_edges=edge_time_parameters(parameters)
    if any(not math.isfinite(float(v)) for k,v in parameters.items() if k!="levels_v"):
        raise ValueError("Template parameters must be finite")
    period=float(parameters.get("period_us",100 if mode==24 else PERIOD_US[mode]))
    if mode==9 and "period_us" not in parameters: period={3:60,5:100,6:225,7:50}[topology]
    if mode==11 and topology in (6,7) and "period_us" not in parameters: period={6:60,7:120}[topology]
    if mode==12 and topology==6 and "period_us" not in parameters: period=210
    if period<=0: raise ValueError("period_us must be positive")
    # Keep the old envelope/compiler unchanged. New width/gap controls accept
    # actual microseconds and are converted into its reference coordinates.
    frequency=float(binding_frequency(binding,1e6/period))
    time_factor=period*frequency/1e6
    for key in ("vin_width_us","gate_width_us","vin_frequency_khz","gate_frequency_khz","vin_period_us","gate_period_us","first_stage_us","second_stage_us"):
        if key in parameters and float(parameters[key])<=0: raise ValueError(key+" must be positive")
    if "pulse_gap_us" in parameters and float(parameters["pulse_gap_us"])<0:
        raise ValueError("脉冲间隔不能为负数")
    if "pulse_gap_us" in parameters and mode not in (3,12,20,22):
        raise ValueError("独立脉冲间隔用于模式 03、12、20、22")
    if "vin_frequency_khz" in parameters and mode not in (11,12): raise ValueError("Vin 脉冲频率用于模式 11、12")
    if "vin_duty_percent" in parameters:
        if mode not in (11,12) or not 0<float(parameters["vin_duty_percent"])<100:
            raise ValueError("模式 11、12 的 Vin 占空比必须在 0～100% 之间")
    if "gate_frequency_khz" in parameters and mode not in (10,11): raise ValueError("Vgate 正弦频率用于模式 10、11")
    if "vin_period_us" in parameters:
        positive_time(parameters["vin_period_us"],"Vin 方波单周期时长")
        if mode not in (11,12): raise ValueError("Vin 方波单周期时长用于模式 11、12")
        if any(k in parameters for k in ("vin_frequency_khz","pulse_period_us","pulse_gap_us")):
            raise ValueError("Vin 单周期时长与其他脉冲周期 / 间隔设置只能填写一种")
    if "gate_period_us" in parameters:
        positive_time(parameters["gate_period_us"],"Vgate 正弦单周期时长")
        if mode!=11: raise ValueError("Vgate 正弦单周期时长用于模式 11")
        if any(k in parameters for k in ("gate_frequency_khz","gate_sine_period_us")):
            raise ValueError("Vgate 单周期时长与旧版正弦设置只能填写一种")
    if any(key in parameters for key in LEVEL_KEYS) and mode not in (15,21):
        raise ValueError("三档电压用于模式 15、21")
    if "pulse_count" in parameters and (float(parameters["pulse_count"])!=int(parameters["pulse_count"]) or not 1<=int(parameters["pulse_count"])<=1000):
        raise ValueError("pulse_count must be an integer in 1..1000")
    low,high=case[signal+"_range_v"]
    vin_peak=case["vin_range_v"][1]; gate_peak=case["gate_range_v"][1]
    identifier=case.get("source_experiment",case["experiment"]).lower()
    notes=["Reference timing is reconstructed from HTML text/plots; not original CSV."]
    edge=float(parameters.get("rise_us",.02))
    fall=float(parameters.get("fall_us",.02))
    if edge<0 or fall<0: raise ValueError("rise_us/fall_us must be nonnegative")
    points=[]

    def transition(a,b,default,available):
        if a==b:return 0
        key="rise_time_us" if b>a else "fall_time_us"
        duration=actual_edges[key]*time_factor if key in actual_edges else default
        if duration>available+1e-9:
            raise ValueError("上升/下降时间超过可用脉宽或分段时长；请缩短边沿或增大脉宽")
        return duration

    def pulse_edges(level,baseline,width):
        incoming="rise_time_us" if level>baseline else "fall_time_us"
        outgoing="fall_time_us" if level>baseline else "rise_time_us"
        explicit_r=incoming in actual_edges or "rise_us" in parameters
        explicit_f=outgoing in actual_edges or "fall_us" in parameters
        r=actual_edges[incoming]*time_factor if incoming in actual_edges else edge if explicit_r else min(edge,width/2)
        f=actual_edges[outgoing]*time_factor if outgoing in actual_edges else fall if explicit_f else min(fall,width/2)
        if not explicit_r:r=min(r,max(0,width-f))
        if not explicit_f:f=min(f,max(0,width-r))
        if r+f>width+1e-9:
            raise ValueError("上升时间与下降时间之和不能超过脉宽；请增大脉宽或缩短边沿")
        return r,f

    def train(pulses, baseline=0.0):
        points[:]=[(0.0,baseline)]
        end=-1.0
        for start,width,level in sorted(pulses):
            if width<=0 or start<end-1e-9: raise ValueError("脉宽必须大于 0，脉冲组不能重叠；请减小脉宽/间隔或分别选择 near/far")
            if start<0 or start+width>period+1e-9: raise ValueError("脉冲超出当前时窗：请缩短脉宽/间隔，或增大整组时窗时长")
            r,f=pulse_edges(level,baseline,width)
            rise_end=start+r; fall_start=start+width-f
            if math.isclose(r+f,width,rel_tol=1e-12,abs_tol=1e-12): fall_start=rise_end
            points.extend([(start,baseline),(rise_end,level),(fall_start,level),(start+width,baseline)])
            end=start+width
        points.append((period,baseline))
        return Waveform(period,points=points,notes=notes)

    def dc(value): return Waveform(period,constant=value,notes=notes)
    def width_for(default,which=signal):
        key="vin_width_us" if which=="vin" else "gate_width_us"
        return float(parameters[key])*time_factor if key in parameters else float(parameters.get("width_us",default))
    def pulse_group(level,which,baseline=0):
        width=width_for(22,which)
        gap=float(parameters["pulse_gap_us"])*time_factor if "pulse_gap_us" in parameters else 22
        start=float(parameters.get("start_us",20)); count=int(parameters.get("pulse_count",3))
        return train([(start+i*(width+gap),width,level) for i in range(count)],baseline)
    def window(level,start=20,width=100,baseline=0):
        return train([(float(parameters.get("start_us",start)),width_for(width),level)],baseline)
    if mode==24:
        start=float(parameters.get("start_us",10)); width=float(parameters.get("width_us",10))
        if start<=0 or width<=0 or start+width>=period:
            raise ValueError("静态扫描要求 0 < 开始时刻、脉宽，且脉冲在时窗结束前归零")
        return (dc(1) if signal=="gate" else window(1,start,width)),entry,case
    def ramp(level,start,rise,width):
        start=float(parameters.get("start_us",start))
        rise=float(parameters.get("ramp_us",rise))
        width=width_for(width)
        rise=transition(0,level,rise,width)
        ending=transition(level,0,fall,period-start-width)
        if rise<0 or rise>width: raise ValueError("ramp_us must be in 0..width_us")
        return Waveform(period,points=[(0,0),(start,0),(start+rise,level),
            (start+width,level),(start+width+ending,0),(period,0)],notes=notes)

    if high==low==0: return dc(0),entry,case

    if mode in (11,12):
        # User-confirmed physical protocol: integrator Gate is a DC bias.
        if mode==12 and signal=="gate": return dc(gate_peak),entry,case
        single="single" in identifier or component=="single"
        none="no_input" in identifier or "control_none" in identifier
        if mode==11:
            if topology==6: width,interval,count,sine_period=.77,2.,10,2.
            elif topology==7: width,interval,count,sine_period=.5,2.,10,2.
            else: width,interval,count,sine_period=1.8,6.,10,12.
            if "p12" in identifier or ("_m11_1" in identifier): interval=12.
            if "offset" in identifier: interval=1.7
            if "fast1" in identifier: interval=3.
            if "p6" in identifier: interval=6.
            start=float(parameters.get("start_us",20))
            if topology==7:
                interval=.7 if "fast0" in identifier else 1.2
                if single and "start_us" not in parameters: start=28
            if topology==6 and "offset" in identifier and "start_us" not in parameters: start+=.5
            if "vin_frequency_khz" in parameters:
                if "pulse_period_us" in parameters: raise ValueError("Vin 频率与旧脉冲周期只能填写一个")
            intervals=[(start,float(parameters.get("pulse_period_us",interval)),1 if single else int(parameters.get("pulse_count",count)))]
        else:
            if topology==6: width,near,far=.47,1.2,15.
            elif topology==7: width,near,far=.66,1.7,9.
            else: width,near,far=1.4,5.4,9.4
            if "integration_c1n_w0.05" in identifier: width=.05
            start=float(parameters.get("start_us",20))
            count=1 if single else int(parameters.get("pulse_count",6))
            if component=="far" or (component not in ("near","single") and case.get("pulse_group")=="far"):
                intervals=[(start,far,count)]
            elif single: intervals=[(start,near,1)]
            else: intervals=[(start,near,count)]
        default_width=width
        width=width_for(width,"vin")
        pulses=[]
        if not none:
            for start,interval,count in intervals:
                default_duty=default_width/interval
                if "vin_period_us" in parameters:
                    interval=float(parameters["vin_period_us"])*time_factor
                elif "vin_frequency_khz" in parameters:
                    interval=1000/float(parameters["vin_frequency_khz"])*time_factor
                elif mode==12 and "pulse_gap_us" in parameters:
                    if "pulse_period_us" in parameters: raise ValueError("脉冲间隔与旧脉冲周期只能填写一个")
                    interval=width+float(parameters["pulse_gap_us"])*time_factor
                elif mode==12 and "vin_width_us" in parameters and "pulse_period_us" not in parameters:
                    interval=width+(interval-default_width)
                else: interval=float(parameters.get("pulse_period_us",interval))
                if "vin_duty_percent" in parameters:
                    width=interval*float(parameters["vin_duty_percent"])/100
                elif any(k in parameters for k in ("vin_period_us","vin_frequency_khz")) and not any(k in parameters for k in ("vin_width_us","width_us")):
                    width=interval*default_duty
                if count<1 or count>1000 or interval<width: raise ValueError("Vin 脉宽不能超过内部方波单周期时长；请调整单周期时长或占空比")
                for index in range(count): pulses.append((start+index*interval,width,vin_peak))
        if signal=="vin": return train(pulses),entry,case
        if mode==11:
            sine_period=1000/float(parameters["gate_frequency_khz"])*time_factor if "gate_frequency_khz" in parameters else float(parameters.get("gate_sine_period_us",sine_period))
            if "gate_period_us" in parameters: sine_period=float(parameters["gate_period_us"])*time_factor
            if sine_period<=0: raise ValueError("gate_sine_period_us must be positive")
            # Align the sine maximum with the center of the first Vin pulse.
            # Recompute the origin when pulse width/duty or start time changes.
            # Keep the sine continuous before the pulse train as well as after it.
            origin=intervals[0][0]+width/2
            wave=Waveform(period,analytic=lambda t:gate_peak*.5*(1+math.cos(2*math.pi*(t-origin)/sine_period)),notes=notes,sine_period=sine_period)
            if "gate_period_us" in parameters:
                wave.continuity_multiple=(1000000/binding_frequency(binding,1e6/period)/positive_time(parameters["gate_period_us"],"Vgate 单周期时长")).denominator
            elif "gate_frequency_khz" in parameters:
                # Derive continuity from exact entered frequencies, not a rounded period.
                wave.continuity_multiple=(Fraction(str(parameters["gate_frequency_khz"]))*1000/binding_frequency(binding,1e6/period)).denominator
            return wave,entry,case
        return dc(gate_peak),entry,case

    if mode in (13,14,19,20):
        lo,hi=case["vin_range_v"]
        level=lo if lo<0 else hi
        baseline=hi if lo<0 and hi>0 else 0
        if signal=="gate": return dc(gate_peak),entry,case
        if mode==20: return pulse_group(level,"vin",baseline),entry,case
        return window(level,20,60 if mode==19 else 70,baseline),entry,case

    if mode in (15,21):
        selected={"low":0,"mid":1,"high":2}.get(component)
        levels=([5.8,6.3,7.3] if topology==6 and mode==15 else
                [3.,4.7,5.] if topology==6 and mode==21 else
                [high*.6,high*.85,high] if mode==21 else [gate_peak/3,gate_peak*2/3,gate_peak])
        if "levels_v" in parameters:
            levels=[float(v) for v in parameters["levels_v"]]
            if len(levels)!=3 or not all(math.isfinite(v) for v in levels): raise ValueError("levels_v needs three finite values")
        if absolute_levels(binding):
            reference_peak=max(abs(v) for v in case[signal+"_range_v"])
            amplitude=float(binding.get("amplitude_v",min(10,reference_peak)))
            defaults=[v*amplitude/reference_peak if reference_peak else 0 for v in levels]
            levels=[float(parameters.get(key,value)) for key,value in zip(LEVEL_KEYS,defaults)]
            if any(abs(v)>10 for v in levels): raise ValueError("三档电压必须在 -10～10 V 范围内")
        starts=[20,75,130] if selected is None else [20]
        indexes=[0,1,2] if selected is None else [selected]
        if mode==15:
            values=[vin_peak]*len(starts) if signal=="vin" else [levels[k] for k in indexes]
            width=width_for(28)
        elif signal=="gate": return dc(gate_peak),entry,case
        else:
            values=[levels[k] for k in indexes]; width=width_for(3.2)
        return train([(t,width,v) for t,v in zip(starts,values)]),entry,case

    if mode==22:
        if signal=="gate": return dc(gate_peak),entry,case
        gap_match=re.search(r"gap([0-9.]+)",identifier)
        gap=float(parameters.get("gap_us",float(gap_match[1]) if gap_match else .1))
        width=width_for(1.0); start=float(parameters.get("start_us",20.))
        if "pulse_gap_us" in parameters:
            if "gap_us" in parameters: raise ValueError("脉冲间隔与旧双脉冲间隔只能填写一个")
            second=start+width+float(parameters["pulse_gap_us"])*time_factor
        else:
            _,ending=pulse_edges(vin_peak,0,width)
            if gap<ending: raise ValueError("gap_us is measured from the falling-edge start and must cover fall_us")
            second=start+width-ending+gap
        pulses=[(start,width,vin_peak),(second,width,vin_peak)]
        if component=="first" or (component=="pair" and "single1" in identifier): pulses=pulses[:1]
        elif component=="second" or (component=="pair" and "single2" in identifier): pulses=pulses[1:]
        return train(pulses),entry,case

    if (mode in (5,6) and signal=="gate") or (mode==7 and signal=="vin"):
        initial=(vin_peak if mode==7 else (3.6 if mode==5 else 3.4) if topology==7 else gate_peak)
        final=vin_peak if mode==7 else gate_peak if topology==7 else 6.3 if topology==6 else gate_peak*2/3
        if absolute_levels(binding):
            peak=max(abs(v) for v in case[signal+"_range_v"])
            scale=float(binding.get("amplitude_v",min(10,peak)))/peak if peak else 0
            initial*=scale; final*=scale
        initial=float(parameters.get(signal+"_initial_v",initial))
        final=float(parameters.get(signal+"_final_v",final))
        if mode in (5,7):
            initial=float(parameters.get("stage1_voltage_v",initial))
            final=float(parameters.get("stage2_voltage_v",final))
        if max(abs(initial),abs(final))>10: raise ValueError("起止电压必须在 -10～10 V 范围内")
        start=float(parameters.get("start_us",20)); width=width_for(100 if mode==7 else 140)
        default_duration=80 if mode==7 else 40 if mode==5 and topology==7 else 70 if mode==5 else width
        duration=float(parameters["first_stage_us"])*time_factor if "first_stage_us" in parameters else float(parameters.get("ramp_us",default_duration))
        if mode in (5,7) and ("first_stage_us" in parameters or "second_stage_us" in parameters):
            second=float(parameters["second_stage_us"])*time_factor if "second_stage_us" in parameters else (100 if mode==7 else 140)-default_duration
            width=duration+second
        if duration<0 or duration>width: raise ValueError("第一段时长不能超过当前通道脉宽；请增大脉宽或缩短第一段")
        if mode!=7 and "rise_us" in parameters and "rise_time_us" not in actual_edges and edge>duration:
            raise ValueError("上升时间不能超过第一段持续时间")
        if mode==5 and topology==7:
            incoming=transition(0,initial,min(edge,duration),duration)
            middle=transition(initial,final,0,width-duration)
            points=[(0,0),(start,0),(start+incoming,initial),(start+duration,initial),(start+duration+middle,final)]
        elif mode==7:
            incoming=transition(0,initial,duration,duration)
            middle=transition(initial,final,0,width-duration)
            points=[(0,0),(start,0),(start+incoming,initial)]
            if incoming<duration:points.append((start+duration,initial))
            points.append((start+duration+middle,final))
        else:
            incoming=transition(0,initial,min(edge,duration),duration)
            points=[(0,0),(start,0),(start+incoming,initial),(start+duration,final)]
        ending=transition(final,0,fall,period-start-width)
        points += [(start+width,final),(start+width+ending,0),(period,0)]
        return Waveform(period,points=points,notes=notes),entry,case

    if signal=="vin":
        if mode in (7,23): return ramp(vin_peak,20,80 if mode==7 else 100,100 if mode==7 else 140),entry,case
        if mode==18:
            slow="rise80" in identifier
            return ramp(vin_peak,20,80 if slow else .02,130),entry,case
        if mode==9: return window(vin_peak,50 if topology==6 else 20,3 if topology in (6,7) else 6),entry,case
        return window(vin_peak,20,140 if mode in (3,4,5,6,10,16) else 300 if mode==8 else 60 if mode==17 else 100),entry,case

    if mode==3: return pulse_group(gate_peak,"gate"),entry,case
    if mode==4: return window(gate_peak,20,22),entry,case
    if mode==10:
        if "flat" in identifier: return dc(gate_peak),entry,case
        floor=float(parameters.get("gate_floor_v",1.0 if topology in (3,5) else gate_peak*.7))
        sine_period=1000/float(parameters["gate_frequency_khz"])*time_factor if "gate_frequency_khz" in parameters else float(parameters.get("gate_sine_period_us",period/8))
        if sine_period<=0: raise ValueError("gate_sine_period_us must be positive")
        wave=Waveform(period,analytic=lambda t:(gate_peak+floor)/2-(gate_peak-floor)/2*math.cos(2*math.pi*t/sine_period),notes=notes,sine_period=sine_period)
        if "gate_frequency_khz" in parameters:
            wave.continuity_multiple=(Fraction(str(parameters["gate_frequency_khz"]))*1000/binding_frequency(binding,1e6/period)).denominator
        return wave,entry,case
    if mode==16:
        baseline=float(parameters.get("gate_baseline_v",6.8 if topology==6 else 6 if topology==7 else 2.4))
        return window(gate_peak,80,80,baseline),entry,case
    if mode==18 and topology!=3: return window(gate_peak,20,8),entry,case
    return dc(gate_peak),entry,case
