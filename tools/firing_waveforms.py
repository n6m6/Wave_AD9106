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
            raise ValueError("Template events exceed period_us; increase period_us or adjust timing")

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
             "gate_floor_v","gate_initial_v","gate_final_v","gate_baseline_v","levels_v"}
    unknown=set(parameters)-allowed
    if unknown: raise ValueError("Unknown template parameters: "+", ".join(sorted(unknown)))
    if any(not math.isfinite(float(v)) for k,v in parameters.items() if k!="levels_v"):
        raise ValueError("Template parameters must be finite")
    period=float(parameters.get("period_us",100 if mode==24 else PERIOD_US[mode]))
    if mode==9 and "period_us" not in parameters: period={3:60,5:100,6:225,7:50}[topology]
    if mode==11 and topology in (6,7) and "period_us" not in parameters: period={6:60,7:120}[topology]
    if mode==12 and topology==6 and "period_us" not in parameters: period=210
    if period<=0: raise ValueError("period_us must be positive")
    low,high=case[signal+"_range_v"]
    vin_peak=case["vin_range_v"][1]; gate_peak=case["gate_range_v"][1]
    identifier=case["experiment"].lower()
    notes=["Reference timing is reconstructed from HTML text/plots; not original CSV."]
    edge=float(parameters.get("rise_us",.02)); fall=float(parameters.get("fall_us",.02))
    if edge<0 or fall<0: raise ValueError("rise_us/fall_us must be nonnegative")
    points=[]

    def train(pulses, baseline=0.0):
        points[:]=[(0.0,baseline)]
        end=-1.0
        for start,width,level in sorted(pulses):
            if width<=0 or start<end-1e-9: raise ValueError("Pulse widths must be positive and pulses cannot overlap")
            if start<0 or start+width>period+1e-9: raise ValueError("Pulse outside reference period")
            r=min(edge,width/2); f=min(fall,width/2)
            points.extend([(start,baseline),(start+r,level),(start+width-f,level),(start+width,baseline)])
            end=start+width
        points.append((period,baseline))
        return Waveform(period,points=points,notes=notes)

    def dc(value): return Waveform(period,constant=value,notes=notes)
    def window(level,start=20,width=100,baseline=0):
        return train([(float(parameters.get("start_us",start)),float(parameters.get("width_us",width)),level)],baseline)
    if mode==24:
        start=float(parameters.get("start_us",10)); width=float(parameters.get("width_us",10))
        if start<=0 or width<=0 or start+width>=period:
            raise ValueError("静态扫描要求 0 < 开始时刻、脉宽，且脉冲在时窗结束前归零")
        return (dc(1) if signal=="gate" else window(1,start,width)),entry,case
    def ramp(level,start,rise,width):
        start=float(parameters.get("start_us",start)); rise=float(parameters.get("ramp_us",rise))
        width=float(parameters.get("width_us",width))
        if rise<0 or rise>width: raise ValueError("ramp_us must be in 0..width_us")
        return Waveform(period,points=[(0,0),(start,0),(start+rise,level),
            (start+width,level),(start+width+fall,0),(period,0)],notes=notes)

    if high==low==0: return dc(0),entry,case

    if mode in (11,12):
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
                if single: start=28
            if topology==6 and "offset" in identifier: start+=.5
            intervals=[(start,float(parameters.get("pulse_period_us",interval)),1 if single else int(parameters.get("pulse_count",count)))]
        else:
            if topology==6: width,near,far=.47,1.2,15.
            elif topology==7: width,near,far=.66,1.7,9.
            else: width,near,far=1.4,5.4,9.4
            if "integration_c1n_w0.05" in identifier: width=.05
            start=float(parameters.get("start_us",20))
            count=1 if single else int(parameters.get("pulse_count",6))
            if component=="near": intervals=[(start,near,count)]
            elif component=="far": intervals=[(start,far,count)]
            elif single: intervals=[(start,near,1)]
            else: intervals=[(start,near,count),(100 if topology!=6 else 110,far,count)]
        width=float(parameters.get("width_us",width))
        pulses=[]
        if not none:
            for start,interval,count in intervals:
                interval=float(parameters.get("pulse_period_us",interval))
                if count<1 or count>1000 or interval<width: raise ValueError("Invalid pulse_count/pulse_period_us")
                for index in range(count): pulses.append((start+index*interval,width,vin_peak))
        if mode==11 and topology==7 and "control_repeat" in identifier:
            pulses += [(t+50,w,v) for t,w,v in pulses]
        if signal=="vin": return train(pulses),entry,case
        if mode==11:
            if topology!=7:
                sine_period=float(parameters.get("gate_sine_period_us",sine_period))
                if sine_period<=0: raise ValueError("gate_sine_period_us must be positive")
                return Waveform(period,analytic=lambda t:gate_peak*.5*(1-math.cos(2*math.pi*t/sine_period)),notes=notes,sine_period=sine_period),entry,case
            if "constant_gate" in identifier: return dc(gate_peak),entry,case
            if "control_repeat" in identifier:
                return train([(28,6,gate_peak),(78,6,gate_peak)]),entry,case
            return window(gate_peak,20 if "early_gate" in identifier else 28,6),entry,case
        if topology==6 and "fixed_gate" not in identifier:
            # Figure shows short synchronous NOTCHES, not positive Gate pulses.
            notches=[(t,min(w,.43),0) for t,w,_ in pulses]
            return train(notches,gate_peak),entry,case
        return dc(gate_peak),entry,case

    if mode in (13,14,19,20):
        lo,hi=case["vin_range_v"]
        level=lo if lo<0 else hi
        baseline=hi if lo<0 and hi>0 else 0
        if signal=="gate": return dc(gate_peak),entry,case
        if mode==20: return train([(20,22,level),(64,22,level),(108,22,level)],baseline),entry,case
        return window(level,20,60 if mode==19 else 70,baseline),entry,case

    if mode in (15,21):
        selected={"low":0,"mid":1,"high":2}.get(component)
        levels=([5.8,6.3,7.3] if topology==6 and mode==15 else
                [3.,4.7,5.] if topology==6 and mode==21 else
                [high*.6,high*.85,high] if mode==21 else [gate_peak/3,gate_peak*2/3,gate_peak])
        if "levels_v" in parameters:
            levels=[float(v) for v in parameters["levels_v"]]
            if len(levels)!=3 or not all(math.isfinite(v) for v in levels): raise ValueError("levels_v needs three finite values")
        starts=[20,75,130] if selected is None else [20]
        indexes=[0,1,2] if selected is None else [selected]
        if mode==15:
            values=[vin_peak]*len(starts) if signal=="vin" else [levels[k] for k in indexes]
            width=float(parameters.get("width_us",28))
        elif signal=="gate": return dc(gate_peak),entry,case
        else:
            values=[levels[k] for k in indexes]; width=float(parameters.get("width_us",3.2))
        return train([(t,width,v) for t,v in zip(starts,values)]),entry,case

    if mode==22:
        if signal=="gate": return dc(gate_peak),entry,case
        gap_match=re.search(r"gap([0-9.]+)",identifier)
        gap=float(parameters.get("gap_us",float(gap_match[1]) if gap_match else .1))
        width=float(parameters.get("width_us",1.0)); start=float(parameters.get("start_us",20.))
        if gap<fall: raise ValueError("gap_us is measured from the falling-edge start and must cover fall_us")
        pulses=[(start,width,vin_peak),(start+width-min(fall,width/2)+gap,width,vin_peak)]
        if component=="first" or (component=="pair" and "single1" in identifier): pulses=pulses[:1]
        elif component=="second" or (component=="pair" and "single2" in identifier): pulses=pulses[1:]
        return train(pulses),entry,case

    if signal=="vin":
        if mode in (7,23): return ramp(vin_peak,20,80 if mode==7 else 100,100 if mode==7 else 140),entry,case
        if mode==18:
            slow="rise80" in identifier
            return ramp(vin_peak,20,80 if slow else .02,130),entry,case
        if mode==9: return window(vin_peak,50 if topology==6 else 20,3 if topology in (6,7) else 6),entry,case
        return window(vin_peak,20,140 if mode in (3,4,5,6,10,16) else 300 if mode==8 else 60 if mode==17 else 100),entry,case

    if mode==3: return train([(20,22,gate_peak),(64,22,gate_peak),(108,22,gate_peak)]),entry,case
    if mode==4: return window(gate_peak,20,22),entry,case
    if mode in (5,6):
        initial=(3.6 if mode==5 else 3.4) if topology==7 else gate_peak
        final=gate_peak if topology==7 else 6.3 if topology==6 else gate_peak*2/3
        initial=float(parameters.get("gate_initial_v",initial)); final=float(parameters.get("gate_final_v",final))
        start=float(parameters.get("start_us",20)); duration=float(parameters.get("ramp_us",70 if mode==5 else 140))
        end=start+float(parameters.get("width_us",140))
        if duration<edge or start+duration>end: raise ValueError("Gate ramp must fit inside its active window")
        if mode==5 and topology==7:
            points=[(0,0),(start,0),(start+edge,initial),(start+40,initial),(start+40,final),(end,final),(end+fall,0),(period,0)]
        else:
            points=[(0,0),(start,0),(start+edge,initial),(start+duration,final),(end,final),(end+fall,0),(period,0)]
        return Waveform(period,points=points,notes=notes),entry,case
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
