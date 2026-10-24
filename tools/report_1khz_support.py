"""Offline support report for selective 1 kHz SRAM playback, no serial I/O."""
import json
from pathlib import Path
from ad9106_firing import compile_scene
from firing_gui_core import load_catalog

ROOT=Path(__file__).resolve().parents[1]

def main():
    catalog=load_catalog(); rows=[]
    for entry in catalog['modes']:
        for case in entry['cases']:
            for component in entry['components']:
                for signal in ('vin','gate'):
                    b=dict(channel=1,topology=entry['topology'],mode=entry['mode'],
                           variant=case['variant'],component=component,signal=signal,frequency_hz=1000)
                    if entry['mode']==24:
                        b['parameters']=dict(period_us=1000,start_us=10,width_us=10)
                    row=dict(b)
                    try:
                        plan=compile_scene({'channels':[b]},catalog)
                        c=plan['channels'][0]
                        row.update(status='dc' if c['source']=='constant' else 'supported',
                                   storage_mode=plan['storage_mode'],hold=plan['hold'],
                                   sram_words=plan['sram_words'],actual_hz=c['frequency_hz'],
                                   snapped=c['snapped_short_plateaus'])
                    except ValueError as e:
                        row.update(status='rejected',reason=str(e))
                    rows.append(row)
    out=ROOT/'docs/firing_verification/selective_1khz'
    out.mkdir(parents=True,exist_ok=True)
    counts={key:sum(r['status']==key for r in rows) for key in ('supported','dc','rejected')}
    (out/'support.json').write_text(json.dumps(dict(
        caveat='Single channel, default amplitude and timing except static period=1000 us. Multi-channel scenes require a separate joint compile. DC is not a 1 kHz waveform.',
        counts=counts,rows=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print(counts)
    for topology in (3,5,6,7):
        for signal in ('vin','gate'):
            modes=sorted({r['mode'] for r in rows if r['status']=='supported' and r['topology']==topology and r['signal']==signal})
            print('Topology {} {} supported mode(s), at least one variant/component: {}'.format(topology,signal,modes))

if __name__=='__main__': main()
