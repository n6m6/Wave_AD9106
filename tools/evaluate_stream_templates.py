"""Report 1 kHz template detail that a future SPI streaming engine must retain.

Offline analysis only. Does not change scenes, the GUI or FPGA configuration.
Flat segment and carrier limits are necessary checks, not analog fidelity proof.
"""
import json
from pathlib import Path
from firing_waveforms import make_waveform

ROOT=Path(__file__).resolve().parents[1]

def main():
    catalog=json.loads((ROOT/'waveforms/firing_catalog.json').read_text(encoding='utf-8'))
    rows=[]
    for entry in catalog['modes']:
        for case in entry['cases']:
            for component in entry['components']:
                for signal in ('vin','gate'):
                    binding=dict(topology=entry['topology'],mode=entry['mode'],
                                 variant=case['variant'],component=component,signal=signal)
                    wave,_,_=make_waveform(catalog,binding)
                    scale=1000/wave.period_us
                    plateaus=[(b[0]-a[0])*scale for a,b in zip(wave.points,wave.points[1:])
                              if a[1]==b[1] and b[0]-a[0]>1e-7]
                    rows.append(dict(**binding,constant=wave.constant is not None,
                        min_flat_segment_us=min(plateaus) if plateaus else None,
                        sine_period_us=wave.sine_period_us*scale if wave.sine_period_us else None,
                        continuity_multiple=wave.continuity_multiple))
    result=dict(envelope_hz=1000,templates=len(rows),
                caveat='Timing features only; no board capture or analog fidelity certification.',
                rows=rows)
    path=ROOT/'docs/firing_verification/stream_evaluation'
    path.mkdir(parents=True,exist_ok=True)
    (path/'templates_1khz.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Templates:',len(rows))
    for limit in (10,5,2.5):
        short=[r for r in rows if r['min_flat_segment_us'] is not None and r['min_flat_segment_us']<limit]
        carrier=[r for r in rows if r['sine_period_us'] and r['sine_period_us']<8*limit]
        print('Update grid {:g} us: {} with shorter flat segments, {} sine carriers below 8 points/cycle'.format(limit,len(short),len(carrier)))
    for r in sorted((r for r in rows if r['min_flat_segment_us']),key=lambda r:r['min_flat_segment_us'])[:4]:
        print(r)

if __name__=='__main__': main()
