"""Finite two-channel rhythm experiments with independent sampled carriers."""
import math

from ad9106_firing import voltage_code, encode_words
from firing_waveforms import make_waveform, binding_frequency, binding_phase, binding_time_offset, rhythm_binding, positive_time, edge_time_parameters, rhythm_square_value


def compile_rhythm_modes(config,catalog):
    active=[b for b in config.get('channels',[]) if b.get('enabled',True)]
    if len(active)!=2 or {b.get('signal') for b in active}!={'vin','gate'}:
        raise ValueError('节律模式需要一对启用的 Vin / Vgate，请关闭其他通道')
    if len({int(b['mode']) for b in active})!=1 or int(active[0]['mode']) not in (27,28):
        raise ValueError('配对两路请选择相同的节律模式 27 或 28')
    windows={positive_time(b.get('duration_us',200),'节律观察时长') for b in active}
    if len(windows)!=1:raise ValueError('节律配对两路的观察时长必须一致')
    if len({int(b['topology']) for b in active})!=1:raise ValueError('节律配对两路的拓扑必须一致')
    synthetic={**config,'rhythm_modulation':{'duration_us':float(next(iter(windows)))},'channels':[
        rhythm_binding(b) if b.get('enabled',True) else dict(b) for b in config['channels']]}
    edges={int(b['channel']):edge_time_parameters(b.get('parameters',{})) for b in active}
    plan=compile_rhythm_scene(synthetic,catalog,_edge_times=edges)
    for c in plan['channels']:
        original=next((b for b in active if int(b['channel'])==c['channel']),None)
        if original:
            c['waveform']='sine' if int(original['mode'])==27 and original['signal']=='gate' else 'square'
            c['mode']=int(original['mode'])
    plan['rhythm_modulation']['mode']=int(active[0]['mode'])
    return plan


def finite(value,label,positive=False):
    try:
        number=float(value)
        if isinstance(value,bool) or not math.isfinite(number) or (positive and number<=0):raise ValueError()
        return number
    except (ValueError,TypeError,OverflowError):
        raise ValueError(label+('必须是大于 0 的有限数值' if positive else '必须是有限数值')) from None


def compile_rhythm_scene(config,catalog,_edge_times=None):
    settings=config.get('rhythm_modulation')
    if not isinstance(settings,dict):raise ValueError('节律调制配置必须是对象')
    if config.get('static_pulse'):raise ValueError('节律调制不能与静态扫描同时启用')
    window=finite(settings.get('duration_us',200),'节律观察时长',True)
    clock=finite(config.get('dac_clock_hz',148500000),'DAC 时钟',True)
    fs=finite(config.get('full_scale_v',10),'满量程',True)
    zero=finite(config.get('zero_code_v',0),'零码电压')
    ppm=finite(config.get('max_frequency_error_ppm',1000),'时长误差容限')
    if fs>10 or ppm<0:raise ValueError('无效的电压标定或时长误差容限')
    rows=[];used=set()
    for b in config.get('channels',[]):
        ch=int(b['channel'])
        if ch not in (1,2,3,4) or ch in used:raise ValueError('通道必须是互不重复的 1～4')
        used.add(ch)
        if not b.get('enabled',True):continue
        mode=int(b['mode'])
        if mode not in (25,26) or b.get('signal') not in ('vin','gate'):
            raise ValueError('节律调制仅支持 Vin 标准方波和 Vgate 标准方波/正弦')
        make_waveform(catalog,b)  # Validate standard waveform parameters.
        freq=float(binding_frequency(b));phase=binding_phase(b,freq)
        if not math.isfinite(phase):raise ValueError('节律相位必须是有限数值')
        amp=finite(b.get('amplitude_v',.5),'波形幅值')
        off=finite(b.get('offset_v',.5),'波形电压偏移')
        if amp<0:raise ValueError('波形幅值不能为负数')
        high=voltage_code(off+amp,fs,zero);low=voltage_code(off-amp,fs,zero)
        if amp>0 and high==low:raise ValueError('波形幅值低于 DAC 电压分辨率')
        if amp>0 and window*freq<1e6-1e-6:
            raise ValueError('观察时长至少需要容纳每路的一个完整周期；请增大观察时长')
        edges=edge_time_parameters((_edge_times or {}).get(ch,{}))
        rows.append(dict(binding=b,channel=ch,mode=mode,frequency=freq,phase=phase%1,
                         rise_us=edges.get('rise_time_us',0),fall_us=edges.get('fall_time_us',0),
                         amplitude=amp,offset=off,duty=float(b.get('parameters',{}).get('duty_percent',50))/100))
    if len(rows)!=2 or {r['binding']['signal'] for r in rows}!={'vin','gate'}:
        raise ValueError('节律调制需要恰好两路启用通道，分别为 Vin 和 Vgate；请关闭其他通道')
    vin=next(r for r in rows if r['binding']['signal']=='vin')
    gate=next(r for r in rows if r['binding']['signal']=='gate')
    if vin['mode']!=25:raise ValueError('节律调制的 Vin 必须为方波')
    pair_names={r['binding'].get('pair','') for r in rows}
    if len(pair_names)>1:raise ValueError('节律调制两路的配对标签必须一致')

    candidates=[];capacity=[];resolution=False
    target=window*clock/1e6
    if not math.isfinite(target):raise ValueError('观察时长超出可表示范围')
    for hold in range(1,17):
        active_n=round(target/hold);n=active_n+1  # One final zero-code sample.
        if active_n<1:continue
        ticks=n*hold
        bases=[b for b in range(1,17) if ticks%b==0 and ticks//b<=65535]
        if not bases:continue
        actual_window=active_n*hold/clock*1e6
        error=abs(actual_window/window-1)
        if error*1e6>ppm:continue
        if any(r['amplitude']>0 and clock/hold/r['frequency']<32 for r in rows):
            resolution=True;continue
        if any(r['mode']==25 and r['amplitude']>0 and min(r['duty'],1-r['duty'])*clock/hold/r['frequency']<1 for r in rows):
            resolution=True;continue
        if n>4096:
            capacity.append(n);continue
        memory=[];allocations={};channels=[]
        for ch in range(1,5):
            row=next((r for r in rows if r['channel']==ch),None)
            if row is None:
                channels.append(dict(channel=ch,source='constant',constant_code=0,frequency_hz=0))
                continue
            codes=[]
            for i in range(active_n):
                cycles=i*hold/clock*row['frequency']+row['phase']
                value=rhythm_square_value(cycles,row['frequency'],row['duty'],row['rise_us'],row['fall_us']) if row['mode']==25 else math.sin(2*math.pi*(cycles%1))
                codes.append(voltage_code(row['offset']+row['amplitude']*value,fs,zero))
            codes.append(0)
            b=row['binding'];silent=not any(codes)
            c=dict(channel=ch,source='constant' if silent else 'sram',signal=b['signal'],topology=int(b['topology']),
                   mode=row['mode'],frequency_hz=row['frequency'] if row['amplitude'] else 0,
                   requested_frequency_hz=row['frequency'],cycles_per_frame=row['frequency']*actual_window/1e6,
                   initial_phase_deg=row['phase']*360,time_offset_us=binding_time_offset(b,row['frequency']),
                   duty_percent=row['duty']*100 if row['mode']==25 else None,
                   rise_time_us=row['rise_us'] if row['mode']==25 else None,
                   fall_time_us=row['fall_us'] if row['mode']==25 else None,
                   min_code=min(codes),max_code=max(codes),nominal_min_v=zero+min(codes)*fs/2048,
                   nominal_max_v=zero+max(codes)*fs/2048,snapped_short_plateaus=0,
                   sram_words=0 if silent else n,sampling_warnings=[],time_resolution_ns=hold/clock*1e9,
                   max_phase_quantization_deg=360*row['frequency']*hold/clock)
            if row['mode']==25 and row['amplitude']>0:
                for label,duration in (('上升',row['rise_us']),('下降',row['fall_us'])):
                    step=hold/clock*1e6
                    if 0<duration<step*(1-1e-9):c['sampling_warnings'].append(
                        '{}时间 {:.6g} μs 小于采样间隔 {:.6g} μs，无法精确还原该边沿；请缩短观察窗或增大边沿时间'.format(label,duration,step))
            if silent:c['constant_code']=0
            else:
                key=tuple(codes)
                if key not in allocations:allocations[key]=len(memory);memory.extend(codes)
                c.update(start=allocations[key],stop=allocations[key]+n-1,samples=codes,zero_tail_samples=0)
            channels.append(c)
        if len(memory)>4096:
            capacity.append(len(memory));continue
        candidates.append(((round(error,12),hold,len(memory)),dict(hold=hold,period_base=min(bases),pattern_period=ticks//min(bases),
            pattern_ticks=ticks,samples_per_frame=n,memory=memory,channels=channels,window=actual_window,error=error)))
    if not candidates:
        detail=('去重后至少需要 {} 点，超过共享 4096 点。'.format(min(capacity)) if capacity else '')
        if resolution:detail+='部分候选方案的每周期采样不足 32 点或方波高/低电平短于一个采样间隔。'
        raise ValueError('节律观察窗无法在当前 SRAM/采样/计时约束下实现。'+detail+'请缩短观察时长或调整频率/占空比；不会修改频差或相位差。')
    plan=min(candidates,key=lambda x:x[0])[1]
    actual_window=plan.pop('window');error=plan.pop('error')
    for c in plan['channels']:
        c['shared_with']=[other['channel'] for other in plan['channels'] if c['source']==other['source']=='sram'
                          and c['channel']!=other['channel'] and c['start']==other['start']]
    delta=gate['frequency']-vin['frequency']
    phase=((gate['phase']-vin['phase'])*360+180)%360-180
    plan.update(dac_clock_hz=clock,full_scale_v=fs,zero_code_v=zero,sram_words=len(plan['memory']),
                sram_free_words=4096-len(plan['memory']),sample_interval_us=plan['hold']/clock*1e6,
                frame_frequency_hz=clock/plan['pattern_ticks'],pattern_duration_us=plan['pattern_ticks']/clock*1e6,
                hardware_pattern_repeats=1,frequency_error_ppm=error*1e6,storage_mode='rhythm_sram',
                finite_window=True,
                rhythm_modulation=dict(kind='square_sine' if gate['mode']==26 else 'square_square',
                    vin_channel=vin['channel'],gate_channel=gate['channel'],vin_frequency_hz=vin['frequency'],
                    gate_frequency_hz=gate['frequency'],frequency_difference_hz=delta,initial_phase_difference_deg=phase,
                    requested_duration_us=window,observation_duration_us=actual_window,
                    phase_drift_deg=360*delta*actual_window/1e6,beat_period_us=1e6/abs(delta) if delta else None))
    plan['burst_duration_us']=plan['pattern_duration_us']
    words=[(0x1f,1),(0x20,14),(0x44,0),(0x45,0),(0x1e,4)]
    words.extend((0x6000+i,(v&4095)<<4) for i,v in enumerate(plan['memory']))
    words.append((0x1e,0))
    hold=plan['hold']%16;pbase=plan['period_base']%16
    words.extend([(0x28,hold<<8|pbase<<4|hold),(0x29,plan['pattern_period']),(0x2a,0),(0x2b,0)])
    sources={c['channel']:int(c['source']=='constant') for c in plan['channels']}
    words.extend([(0x26,sources[4]<<8|sources[3]),(0x27,sources[2]<<8|sources[1])])
    for c in plan['channels']:
        ch=c['channel'];delay=0x5c-4*(ch-1)
        words.extend([(0x36-ch,0x4000),(0x26-ch,0),(0x32-ch,0),
                      (delay,0),(delay+1,c.get('start',0)<<4),(delay+2,c.get('stop',0)<<4)])
    packets,oracle=encode_words(words)
    plan.update(register_and_sram_writes=words,spi_oracle=oracle,packets=[p.hex(' ').upper() for p in packets],
                notes=['Both rhythm carriers use the same DAC sample clock and start together.',
                       'One finite observation window per trigger, followed by a zero-code sample. No within-window reset.',
                       'Carrier frequencies are nominal sampling targets; square edges and phase are quantized to the sample grid.',
                       'Different frequencies cause phase drift: delta_phi(t)=delta_phi(0)+360*(fgate-fvin)*t.'])
    return plan
