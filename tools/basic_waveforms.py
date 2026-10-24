"""Finite standard square/DDS sine scenes using the FPGA basic sequencer.

The SPI clock stays at 1 MHz. Timing below is a conservative budget for nine
32-bit writes including RAMUPDATE and the existing 1 us update wait.
"""
import math
from fractions import Fraction
from ad9106_firing import voltage_code, common_frequency, encode_words, HARDWARE_PATTERN_REPEATS
from firing_waveforms import make_waveform

FPGA_HZ=100000000
MIN_EVENT_TICKS=30000
START_TICKS=MIN_EVENT_TICKS

def compile_basic_scene(config,catalog):
    clock=float(config.get('dac_clock_hz',148500000))
    fs=float(config.get('full_scale_v',10)); zero=float(config.get('zero_code_v',0))
    ppm=float(config.get('max_frequency_error_ppm',1000))
    if not all(math.isfinite(x) for x in (clock,fs,zero,ppm)) or clock<=0 or not 0<fs<=10 or ppm<0:
        raise ValueError('Invalid DAC clock/calibration/tolerance')
    rows=[]; used=set(); pairs={}
    for b in config.get('channels',[]):
        ch=int(b['channel'])
        if ch not in (1,2,3,4) or ch in used: raise ValueError('channel must be unique in 1..4')
        used.add(ch)
        if not b.get('enabled',True): continue
        wave,entry,case=make_waveform(catalog,b)
        mode=int(b['mode']); freq=float(b['frequency_hz']); amp=float(b.get('amplitude_v',1)); offset=float(b.get('offset_v',0)); phase=float(b.get('phase_deg',0))
        if not all(math.isfinite(x) for x in (freq,amp,offset,phase)) or freq<=0 or amp<0:
            raise ValueError('Invalid standard waveform parameters')
        if mode not in (25,26) and wave.constant is None:
            raise ValueError('标准方波/正弦模式可与直流通道组合；请关闭其他动态模板通道后发送')
        if b.get('signal') not in ('vin','gate'): raise ValueError('signal must be vin or gate')
        if mode in (25,26):
            voltage_code(offset+amp,fs,zero); voltage_code(offset-amp,fs,zero)
        if mode==25 and phase%360:
            raise ValueError('标准方波当前要求相位为 0°；不同占空比的组合仍需通过事件间隔检查')
        r=dict(binding=b,channel=ch,mode=mode,frequency=freq,amplitude=amp,offset=offset,phase=phase,
               duty=float(b.get('parameters',{}).get('duty_percent',50))/100,
               wave=wave,constant=None)
        if mode not in (25,26) or amp==0:
            peak=max(abs(v) for v in case[b['signal']+'_range_v'])
            r['constant']=voltage_code((wave.constant or 0)*(amp/peak if peak else 0)+offset,fs,zero)
        rows.append(r)
        if b.get('pair'): pairs.setdefault(b['pair'],[]).append(r)
    for name,rs in pairs.items():
        if len(rs)!=2 or {r['binding']['signal'] for r in rs}!={'vin','gate'}:
            raise ValueError('Pair {} needs Vin and Gate'.format(name))
        if rs[0]['frequency']!=rs[1]['frequency']:
            raise ValueError('配对通道频率必须一致')
    dynamic=[r for r in rows if r['constant'] is None]
    sine=[r for r in dynamic if r['mode']==26]
    if len({r['frequency'] for r in sine})>1:
        raise ValueError('AD9106 多路 DDS 正弦共用一个频率；各路幅值、偏移及相位可分别设置')
    base=common_frequency([Fraction(str(r['frequency'])) for r in dynamic]) if dynamic else Fraction(1000)
    # Round the common period upward so finite DDS cycles cannot be clipped.
    tw=round(sine[0]['frequency']/clock*(1<<24)) if sine else 0
    if sine and not 1<=tw<=0x7fffff: raise ValueError('DDS frequency is out of range')
    actual_sine=tw*clock/(1<<24) if sine else 0
    if sine and abs(actual_sine/sine[0]['frequency']-1)*1e6>ppm:
        raise ValueError('DDS 频率量化误差超过当前允许值')
    cycles={r['channel']:int(Fraction(str(r['frequency']))/base) for r in dynamic}
    if any(n>65535 for n in cycles.values()): raise ValueError('公共周期内 DDS 周期数超过寄存器范围')
    target=clock/float(base)
    # Include the trigger-to-pattern latency and DAC/FPGA clock rounding margin.
    if sine: target=max(target,max(cycles[r['channel']]*clock/actual_sine for r in sine)+24)
    choices=[(math.ceil(target/b)*b,b) for b in range(1,17) if math.ceil(target/b)<=65535]
    if not choices: raise ValueError('标准波形公共周期超出芯片周期寄存器范围')
    ticks,pbase=min(choices); frame_ticks=round(ticks/clock*FPGA_HZ)
    frame_s=frame_ticks/FPGA_HZ
    if any(abs((cycles[r['channel']]/frame_s)/r['frequency']-1)*1e6>ppm for r in dynamic if r['mode']==25):
        raise ValueError('方波周期量化误差超过允许值')
    end=START_TICKS+frame_ticks*HARDWARE_PATTERN_REPEATS
    # Events use a single commit for all four channels. Unchanged levels are
    # staged again to keep timing independent of which channels have an edge.
    times={START_TICKS,end}; edges={}
    for r in dynamic:
        if r['mode']!=25: continue
        count=cycles[r['channel']]*HARDWARE_PATTERN_REPEATS
        if count>31: raise ValueError('标准方波公共周期内周期数过多，请使用更接近的通道频率')
        period=frame_ticks/cycles[r['channel']]
        for i in range(count):
            rise=START_TICKS+round(i*period); fall=START_TICKS+round((i+r['duty'])*period)
            if not rise<fall<START_TICKS+round((i+1)*period): raise ValueError('方波脉宽低于计时分辨率')
            times.update((rise,fall))
            edges.setdefault(rise,{})[r['channel']]=True
            edges.setdefault(fall,{})[r['channel']]=False
    times=sorted(times)
    if len(times)>64 or any(b-a<MIN_EVENT_TICKS for a,b in zip([0]+times,times)):
        raise ValueError('方波切换过密：当前四路 SPI 提交至少需要 300 µs 间隔。1 kHz 可用相同 50% 占空比；请降低频率或调整占空比组合，不会自动拉宽脉冲')
    channels=[]; gains={}; offsets={}; constants={}; sources={}; phases={}
    for ch in range(1,5):
        r=next((r for r in rows if r['channel']==ch),None)
        if r is None:
            gains[ch]=0; offsets[ch]=0; constants[ch]=0; sources[ch]=1
            channels.append(dict(channel=ch,source='constant',constant_code=0,frequency_hz=0)); continue
        source='constant' if r['constant'] is not None else 'dds' if r['mode']==26 else 'fpga_square'
        gains[ch]=round(r['amplitude']/fs*1024) if source=='dds' else 1024
        if source=='dds' and r['amplitude']>0 and gains[ch]==0: raise ValueError('正弦幅值低于数字增益分辨率')
        offsets[ch]=voltage_code(r['offset'],fs,zero) if source=='dds' else 0
        constants[ch]=r['constant'] or 0; sources[ch]=0x32 if source=='dds' else 1
        signed_phase=(r['phase']+180)%360-180
        phases[ch]=round(signed_phase/360*65535)&65535
        f=actual_sine if source=='dds' else cycles.get(ch,0)/frame_s if source=='fpga_square' else 0
        amp=gains[ch]/1024*fs if source=='dds' else r['amplitude']
        off=zero+offsets[ch]*fs/2048 if source=='dds' else r['offset']
        # Preview is an analytic guide for DDS and an exact event guide for square.
        size=1000
        phase_signed=phases[ch] if phases[ch]<32768 else phases[ch]-65536
        if source=='dds': values=[voltage_code(off+amp*math.sin(2*math.pi*f*i*frame_s/size+phase_signed*2*math.pi/65535),fs,zero) for i in range(size)]
        elif source=='fpga_square': values=[voltage_code(off+(amp if (i*cycles[ch]/size)%1<r['duty'] else -amp),fs,zero) for i in range(size)]
        else: values=[r['constant']]
        channels.append(dict(channel=ch,source=source,signal=r['binding']['signal'],topology=r['binding']['topology'],mode=r['mode'],
            frequency_hz=f,requested_frequency_hz=r['frequency'],cycles_per_frame=cycles.get(ch,0),
            samples=values,constant_code=constants[ch],min_code=min(values),max_code=max(values),
            nominal_min_v=zero+min(values)*fs/2048,nominal_max_v=zero+max(values)*fs/2048,
            snapped_short_plateaus=0,preview_step_us=frame_s*1e6/size,phase_word=phases[ch],
            duty_percent=r['duty']*100 if source=='fpga_square' else None))
    events=[]; levels={}
    for t in times:
        levels.update(edges.get(t,{}))
        codes={ch:constants[ch] for ch in range(1,5)}
        for r in dynamic:
            if r['mode']==25:
                high=levels.get(r['channel'],False)
                codes[r['channel']]=voltage_code(r['offset']+(r['amplitude'] if high else -r['amplitude']),fs,zero)
        final=t==end
        values=[t>>16,t&65535]+[0 if final else (codes[ch]&4095)<<4 for ch in (4,3,2,1)]+[0 if final else gains[ch]<<4 for ch in (4,3,2,1)]
        events.append(dict(ticks=t,words=values))
    words=[(0x7100,0),(0x1f,1),(0x20,14),(0x44,0),(0x45,0),
           (0x28,0x100|(pbase%16)<<4|1),(0x29,ticks//pbase),
           (0x2a,0x0101),(0x2b,0x0101),(0x26,sources[4]<<8|sources[3]),(0x27,sources[2]<<8|sources[1]),
           (0x3e,tw>>8),(0x3f,(tw&255)<<8)]
    for ch in range(1,5):
        delay=0x5c-4*(ch-1)
        words.extend([(0x36-ch,0),(0x26-ch,(offsets[ch]&4095)<<4),(0x32-ch,0),
                      (0x44-ch,phases.get(ch,0)),(delay,0),(delay+3,max(1,cycles.get(ch,1)))])
    words.extend((0x7200+i*10+j,v) for i,e in enumerate(events) for j,v in enumerate(e['words']))
    words.extend([(0x7101,len(events)),(0x7100,1)])
    packets,oracle=encode_words(words)
    return dict(dac_clock_hz=clock,full_scale_v=fs,zero_code_v=zero,storage_mode='basic_events',
        frame_frequency_hz=1/frame_s,pattern_ticks=ticks,pattern_period=ticks//pbase,period_base=pbase,hold=1,
        samples_per_frame=round(ticks),sram_words=0,memory=[],frequency_error_ppm=max([abs(actual_sine/sine[0]['frequency']-1)*1e6] if sine else [0]),
        channels=channels,hardware_pattern_repeats=HARDWARE_PATTERN_REPEATS,pattern_duration_us=frame_s*1e6,
        burst_duration_us=end/FPGA_HZ*1e6+2,startup_delay_us=START_TICKS/FPGA_HZ*1e6,
        basic_events=events,dds_tuning_word=tw,register_and_sram_writes=words,
        spi_oracle=[(a,v) for a,v in oracle if a<0x7100],packets=[p.hex(' ').upper() for p in packets],
        notes=['Requires basic-event FPGA firmware. Preview of DDS is analytical, not ADC capture.',
               'DDS channels share one frequency. Square event gaps must be at least 300 us at 1 MHz SPI.'])
