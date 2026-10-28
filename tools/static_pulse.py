"""One finite static pulse; Gate encloses Vin. Uses existing FPGA firmware only."""
import copy
import math

from ad9106_firing import compile_scene, encode_words, voltage_code
from basic_waveforms import FPGA_HZ, MIN_EVENT_TICKS, START_TICKS
from firing_waveforms import Waveform, edge_time_parameters

MAX_TICKS=0xffffffff-3204  # Reserve the existing sequencer's COMMIT_LEAD addition.


def finite(value,label,positive=False):
    try:
        v=float(value)
        if isinstance(value,bool) or not math.isfinite(v) or v<0 or (positive and v==0): raise ValueError()
        return v
    except (ValueError,TypeError,OverflowError):
        raise ValueError(label+('必须大于 0' if positive else '必须为非负有限数值')) from None


def compile_static_pulse(config,catalog):
    if config.get('repeat_count',1)!=1:
        raise ValueError('有限静态扫描每次点击只触发一次；请把触发组数设为 1')
    bindings=[b for b in config.get('channels',[]) if b.get('enabled',True)]
    ids=[int(b['channel']) for b in bindings]
    if len(set(ids))!=len(ids) or any(ch not in (1,2,3,4) for ch in ids):
        raise ValueError('通道必须是互不重复的 1～4')
    if not bindings or any(int(b['mode'])!=24 for b in bindings):
        raise ValueError('有限静态扫描请只启用模式 24；其他动态模板须关闭')
    vin=[b for b in bindings if b.get('signal')=='vin']
    if not vin or any(b.get('signal') not in ('vin','gate') for b in bindings):
        raise ValueError('有限静态扫描至少需要一路 Vin，并在该路设置脉冲持续时间')
    for b in bindings:
        if b.get('time_offset_us',0) or b.get('phase_deg',0):
            raise ValueError('有限静态扫描不使用循环时间偏移；请用 Vgate 提前/延后时间')
    widths={b['channel']:finite(b.get('parameters',{}).get('width_us',2000),'Vin 脉冲持续时间',True) for b in vin}
    gates=[]
    for b in bindings:
        if b['signal']!='gate': continue
        matches=[v for v in vin if b.get('pair') and v.get('pair')==b['pair']]
        if not b.get('pair') and len(vin)==1: matches=vin
        if len(matches)!=1: raise ValueError('每路 Vgate 必须能找到唯一配对的 Vin')
        p=b.get('parameters',{})
        gates.append((b,matches[0],finite(p.get('gate_lead_us',300),'Vgate 提前时间'),
                      finite(p.get('gate_tail_us',300),'Vgate 延后归零时间')))
    lead=max([g[2] for g in gates]+[0])
    spans={b['channel']:(lead,lead+widths[b['channel']]) for b in vin}
    for b,v,pre,post in gates: spans[b['channel']]=(lead-pre,lead+widths[v['channel']]+post)
    duration=max(end for _,end in spans.values())
    clock=float(config.get('dac_clock_hz',148500000)); fs=float(config.get('full_scale_v',10)); zero=float(config.get('zero_code_v',0))
    if not all(math.isfinite(x) for x in (clock,fs,zero)) or clock<=0 or not 0<fs<=10: raise ValueError('无效的时钟或电压标定')
    codes={}; levels={}; edges={}
    for b in bindings:
        amp=float(b.get('amplitude_v',1))
        if not math.isfinite(amp) or amp<0: raise ValueError('脉冲电压幅值必须为非负有限数值')
        levels[b['channel']]=amp+float(b.get('offset_v',0))
        codes[b['channel']]=voltage_code(levels[b['channel']],fs,zero)
        requested=edge_time_parameters(b.get('parameters',{}))
        rise=requested.get('rise_time_us',0);fall=requested.get('fall_time_us',0)
        a,z=spans[b['channel']]
        if rise+fall>z-a+1e-9:
            raise ValueError('上升时间与下降时间之和不能超过脉宽；请增大脉宽或缩短边沿')
        edges[b['channel']]=(fall,rise) if levels[b['channel']]<0 else (rise,fall)
    deadlines=sorted({START_TICKS+round(t*FPGA_HZ/1e6) for span in spans.values() for t in span})
    if deadlines[-1]>MAX_TICKS: raise ValueError('脉冲及包络总时长超出现有 FPGA 32 位定时范围（约 42.95 秒）')
    shaped=any(codes[ch]!=0 and any(edge>0 for edge in times) for ch,times in edges.items())
    if shaped or any(b-a<MIN_EVENT_TICKS for a,b in zip([0]+deadlines,deadlines)):
        # Nonzero edges need sampled ramps. Keep the event path for long, ideal
        # pulses; never ignore requested slew or stretch short event gaps.
        synthetic=copy.deepcopy(config);synthetic.pop('static_pulse',None)
        waves={}; period=duration+.1
        for b in synthetic['channels']:
            if not b.get('enabled',True): continue
            start,end=spans[b['channel']]; value=levels[b['channel']]
            b.update(duration_us=period,amplitude_v=abs(value),offset_v=0,time_offset_us=0,
                     parameters={'period_us':period})
            b.pop('frequency_hz',None);b.pop('phase_deg',None);b.pop('pair',None)
            sign=-1 if value<0 else 1
            rising,falling=edges[b['channel']]
            rise_end=start+rising;fall_start=end-falling
            if math.isclose(rising+falling,end-start,rel_tol=1e-12,abs_tol=1e-12):fall_start=rise_end
            waves[b['channel']]=Waveform(period,points=[(0,0),(start,0),(rise_end,sign),
                (fall_start,sign),(end,0),(period,0)])
        try: plan=compile_scene(synthetic,catalog,_waveforms=waves)
        except ValueError as error:
            reason=('静态扫描的非零上升/下降时间需要 SRAM 生成，当前完整脉冲或包络无法保留所设边沿；请缩短脉宽或包络。'
                    if shaped else '静态扫描的相邻切换不足 300 μs，且完整波形也无法放入 SRAM；请调整提前/延后时间或脉宽。')
            raise ValueError(reason+str(error)) from None
        words=[(a,0 if a in (0x2a,0x2b) else v) for a,v in plan['register_and_sram_writes']]
        packets,oracle=encode_words(words)
        plan.update(register_and_sram_writes=words,spi_oracle=oracle,packets=[p.hex(' ').upper() for p in packets],
                    hardware_pattern_repeats=1,burst_duration_us=plan['pattern_duration_us'])
    else:
        events=[]
        tick_spans={ch:(START_TICKS+round(a*FPGA_HZ/1e6),START_TICKS+round(b*FPGA_HZ/1e6)) for ch,(a,b) in spans.items()}
        for t in deadlines:
            active={ch for ch,(a,b) in tick_spans.items() if a<=t<b}
            values=[t>>16,t&65535]+[(codes[ch]&4095)<<4 if ch in active else 0 for ch in (4,3,2,1)]+[0x4000 if ch in active else 0 for ch in (4,3,2,1)]
            events.append({'ticks':t,'words':values})
        # Constant sources are controlled by the finite event table, not by SRAM
        # or the chip's pattern period. The final event explicitly mutes all DACs.
        words=[(0x7100,0),(0x1f,1),(0x20,14),(0x44,0),(0x45,0),
               (0x28,0x111),(0x29,100),(0x2a,0),(0x2b,0),(0x26,0x0101),(0x27,0x0101)]
        for ch in range(1,5): words.extend([(0x36-ch,0),(0x26-ch,0),(0x32-ch,0)])
        words.extend((0x7200+i*10+j,v) for i,e in enumerate(events) for j,v in enumerate(e['words']))
        words.extend([(0x7101,len(events)),(0x7100,1)])
        packets,oracle=encode_words(words)
        plan=dict(dac_clock_hz=clock,full_scale_v=fs,zero_code_v=zero,hold=1,period_base=1,pattern_period=100,
            storage_mode='static_events',frame_frequency_hz=1e6/duration,pattern_duration_us=duration,
            pattern_ticks=round(duration*clock/1e6),samples_per_frame=1000,sram_words=0,memory=[],
            frequency_error_ppm=0,hardware_pattern_repeats=1,burst_duration_us=deadlines[-1]/FPGA_HZ*1e6+2,
            startup_delay_us=START_TICKS/FPGA_HZ*1e6,basic_events=events,register_and_sram_writes=words,
            spi_oracle=[(a,v) for a,v in oracle if a<0x7100],packets=[p.hex(' ').upper() for p in packets],channels=[])
        for ch in range(1,5):
            b=next((b for b in bindings if b['channel']==ch),None)
            if b is None: plan['channels'].append(dict(channel=ch,source='constant',constant_code=0,frequency_hz=0));continue
            a,z=tick_spans[ch];actual_start=(a-START_TICKS)/FPGA_HZ*1e6;actual_end=(z-START_TICKS)/FPGA_HZ*1e6
            # Exact event positions, including both sides of each discontinuity.
            points=[(0,0),(actual_start,0),(actual_start,codes[ch]),(actual_end,codes[ch]),(actual_end,0),(duration,0)]
            plan['channels'].append(dict(channel=ch,source='fpga_pulse',signal=b['signal'],topology=b['topology'],mode=24,
                frequency_hz=0,samples=[v for _,v in points],sample_times_us=[t for t,_ in points],
                pulse_width_us=actual_end-actual_start,min_code=min(0,codes[ch]),max_code=max(0,codes[ch]),
                nominal_min_v=zero+min(0,codes[ch])*fs/2048,nominal_max_v=zero+max(0,codes[ch])*fs/2048))
    plan['static_pulse']=True
    plan['notes']=['Single finite static pulse. Gate encloses Vin; all outputs return to DAC zero code.',
                   'Long pulses require the existing basic-event firmware. No PC sleep controls the falling edge.']
    for c in plan['channels']:
        if c['channel'] in spans:
            c.setdefault('pulse_width_us',spans[c['channel']][1]-spans[c['channel']][0])
    return plan
