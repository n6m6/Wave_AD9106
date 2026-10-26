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
                    "vin_duty_percent", "gate_frequency_khz", "first_stage_us", "second_stage_us",
                    "stage1_voltage_v", "stage2_voltage_v", *LEVEL_KEYS}


def absolute_levels(binding):
    """The three individually entered voltages are output targets, not ratios."""
    mode=int(binding["mode"]); signal=binding["signal"]; params=binding.get("parameters",{})
    if (mode,signal) in ((15,"gate"),(21,"vin")):
        return any(key in params for key in LEVEL_KEYS)
    if (mode,signal) in ((5,"gate"),(7,"vin")):
        return any(key in params for key in ("stage1_voltage_v","stage2_voltage_v","gate_initial_v","gate_final_v"))
    return mode==6 and signal=="gate" and any(key in params for key in ("gate_initial_v","gate_final_v"))


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
            raise ValueError("波形超出当前时窗：请缩短各段时间，或降低包络频率以扩大时窗")

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


def make_waveform(catalog, binding):
    topology=int(binding["topology"]); mode=int(binding["mode"])
    entry,case=select_entry(catalog,topology,mode,binding.get("variant",0))
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
    component=binding.get("component",entry["components"][0])
    if component not in entry["components"]: raise ValueError("Invalid component for this mode")
    parameters=binding.get("parameters",{})
    allowed={"period_us","start_us","width_us","rise_us","fall_us","ramp_us",
             "gap_us","pulse_period_us","pulse_count","gate_sine_period_us",
             "gate_floor_v","gate_initial_v","gate_final_v","gate_baseline_v","levels_v"} | EXTRA_PARAMETERS
    unknown=set(parameters)-allowed
    if unknown: raise ValueError("Unknown template parameters: "+", ".join(sorted(unknown)))
    if any(not math.isfinite(float(v)) for k,v in parameters.items() if k!="levels_v"):
        raise ValueError("Template parameters must be finite")
    period=float(parameters.get("period_us",100 if mode==24 else PERIOD_US[mode]))
    if mode==9 and "period_us" not in parameters: period={3:60,5:100,6:225,7:50}[topology]
    if mode==11 and topology in (6,7) and "period_us" not in parameters: period={6:60,7:120}[topology]
    if mode==12 and topology==6 and "period_us" not in parameters: period=210
    if period<=0: raise ValueError("period_us must be positive")
    # Keep the old envelope/compiler unchanged. New width/gap controls accept
    # actual microseconds and are converted into its reference coordinates.
    frequency=float(binding.get("frequency_hz",1e6/period))
    if not math.isfinite(frequency) or frequency<=0: raise ValueError("frequency_hz must be positive and finite")
    time_factor=period*frequency/1e6
    for key in ("vin_width_us","gate_width_us","vin_frequency_khz","gate_frequency_khz","first_stage_us","second_stage_us"):
        if key in parameters and float(parameters[key])<=0: raise ValueError(key+" must be positive")
    if "pulse_gap_us" in parameters and float(parameters["pulse_gap_us"])<0:
        raise ValueError("脉冲间隔不能为负数")
    if "pulse_gap_us" in parameters and mode not in (3,12,20,22):
        raise ValueError("独立脉冲间隔用于模式 03、12、20、22")
    if "vin_frequency_khz" in parameters and mode not in (11,12): raise ValueError("Vin 脉冲频率用于模式 11、12")
    if "vin_duty_percent" in parameters:
        if mode not in (11,12) or not 0<float(parameters["vin_duty_percent"])<100:
            raise ValueError("模式 11、12 的 Vin 占空比必须在 0～100% 之间")
    if "gate_frequency_khz" in parameters and mode!=11: raise ValueError("Vgate 正弦频率用于模式 11")
    if any(key in parameters for key in LEVEL_KEYS) and mode not in (15,21):
        raise ValueError("三档电压用于模式 15、21")
    if "pulse_count" in parameters and (float(parameters["pulse_count"])!=int(parameters["pulse_count"]) or not 1<=int(parameters["pulse_count"])<=1000):
        raise ValueError("pulse_count must be an integer in 1..1000")
    low,high=case[signal+"_range_v"]
    vin_peak=case["vin_range_v"][1]; gate_peak=case["gate_range_v"][1]
    identifier=case.get("source_experiment",case["experiment"]).lower()
    notes=["Reference timing is reconstructed from HTML text/plots; not original CSV."]
    edge=float(parameters.get("rise_us",.02)); fall=float(parameters.get("fall_us",.02))
    if edge<0 or fall<0: raise ValueError("rise_us/fall_us must be nonnegative")
    points=[]

    def train(pulses, baseline=0.0):
        points[:]=[(0.0,baseline)]
        end=-1.0
        for start,width,level in sorted(pulses):
            if width<=0 or start<end-1e-9: raise ValueError("脉宽必须大于 0，脉冲组不能重叠；请减小脉宽/间隔或分别选择 near/far")
            if start<0 or start+width>period+1e-9: raise ValueError("脉冲超出当前时窗：请缩短脉宽/间隔，或降低包络频率以扩大时窗")
            r=min(edge,width/2); f=min(fall,width/2)
            points.extend([(start,baseline),(start+r,level),(start+width-f,level),(start+width,baseline)])
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
        start=float(parameters.get("start_us",start)); rise=float(parameters.get("ramp_us",rise))
        width=width_for(width)
        if rise<0 or rise>width: raise ValueError("ramp_us must be in 0..width_us")
        return Waveform(period,points=[(0,0),(start,0),(start+rise,level),
            (start+width,level),(start+width+fall,0),(period,0)],notes=notes)

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
                if "vin_frequency_khz" in parameters:
                    interval=1000/float(parameters["vin_frequency_khz"])*time_factor
                elif mode==12 and "pulse_gap_us" in parameters:
                    if "pulse_period_us" in parameters: raise ValueError("脉冲间隔与旧脉冲周期只能填写一个")
                    interval=width+float(parameters["pulse_gap_us"])*time_factor
                elif mode==12 and "vin_width_us" in parameters and "pulse_period_us" not in parameters:
                    interval=width+(interval-default_width)
                else: interval=float(parameters.get("pulse_period_us",interval))
                if "vin_duty_percent" in parameters:
                    width=interval*float(parameters["vin_duty_percent"])/100
                elif "vin_frequency_khz" in parameters and not any(k in parameters for k in ("vin_width_us","width_us")):
                    width=interval*default_duty
                if count<1 or count>1000 or interval<width: raise ValueError("Vin 脉宽不能超过内部脉冲周期；请调整内部频率或占空比")
                for index in range(count): pulses.append((start+index*interval,width,vin_peak))
        if signal=="vin": return train(pulses),entry,case
        if mode==11:
            sine_period=1000/float(parameters["gate_frequency_khz"])*time_factor if "gate_frequency_khz" in parameters else float(parameters.get("gate_sine_period_us",sine_period))
            if sine_period<=0: raise ValueError("gate_sine_period_us must be positive")
            wave=Waveform(period,analytic=lambda t:gate_peak*.5*(1-math.cos(2*math.pi*t/sine_period)),notes=notes,sine_period=sine_period)
            if "gate_frequency_khz" in parameters:
                # Derive continuity from exact entered frequencies, not a rounded period.
                wave.continuity_multiple=(Fraction(str(parameters["gate_frequency_khz"]))*1000/Fraction(str(frequency))).denominator
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
            if gap<fall: raise ValueError("gap_us is measured from the falling-edge start and must cover fall_us")
            second=start+width-min(fall,width/2)+gap
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
        if mode==5 and topology==7:
            points=[(0,0),(start,0),(start+min(edge,duration),initial),(start+duration,initial),(start+duration,final)]
        elif mode==7:
            points=[(0,0),(start,0),(start+duration,initial),(start+duration,final)]
        else:
            points=[(0,0),(start,0),(start+min(edge,duration),initial),(start+duration,final)]
        points += [(start+width,final),(start+width+fall,0),(period,0)]
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
        sine_period=float(parameters.get("gate_sine_period_us",period/8))
        if sine_period<=0: raise ValueError("gate_sine_period_us must be positive")
        return Waveform(period,analytic=lambda t:(gate_peak+floor)/2-(gate_peak-floor)/2*math.cos(2*math.pi*t/sine_period),notes=notes,sine_period=sine_period),entry,case
    if mode==16:
        baseline=float(parameters.get("gate_baseline_v",6.8 if topology==6 else 6 if topology==7 else 2.4))
        return window(gate_peak,80,80,baseline),entry,case
    if mode==18 and topology!=3: return window(gate_peak,20,8),entry,case
    return dc(gate_peak),entry,case
