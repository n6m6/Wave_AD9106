"""User-facing microseconds preserve legacy waveforms and serial commands."""
import copy
import json
import unittest
from pathlib import Path

from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_waveforms import binding_frequency, make_waveform
from firing_web import public_preview

ROOT=Path(__file__).resolve().parents[1]
CATALOG=load_catalog()


def timed_scene(scene):
    result=copy.deepcopy(scene)
    for b in result['channels']:
        if 'frequency_hz' in b: b['duration_us']=1e6/b.pop('frequency_hz')
        params=b.get('parameters',{})
        for old,new in (('vin_frequency_khz','vin_period_us'),('gate_frequency_khz','gate_period_us')):
            if old in params: params[new]=1000/params.pop(old)
    return result


def binding(mode=11,signal='vin',**kwargs):
    return dict(channel=1,topology=6,mode=mode,signal=signal,duration_us=50,**kwargs)


class DurationTests(unittest.TestCase):
    def test_sine_frequency_mode10_is_independent_of_envelope_duration(self):
        for duration in (20,50):
            for frequency in (500,700):
                b=binding(10,'gate',parameters={'gate_frequency_khz':frequency})
                b['duration_us']=duration
                wave,_,_=make_waveform(CATALOG,b)
                self.assertAlmostEqual(wave.sine_period_us/wave.period_us*duration,1000/frequency)
                self.assertEqual(wave.continuity_multiple,1)
                plan=compile_scene({'channels':[b]},CATALOG)
                self.assertAlmostEqual(plan['channels'][0]['sine_carrier_hz'],frequency*1000)
                if frequency==500:
                    old=copy.deepcopy(b)
                    old['parameters']={'gate_sine_period_us':2*wave.period_us/duration}
                    self.assertEqual(plan['packets'],compile_scene({'channels':[old]},CATALOG)['packets'])

    def test_existing_example_scenes_produce_identical_packets(self):
        for name in ('example_two_pairs.json','example_basic_1khz.json'):
            old=json.loads((ROOT/'waveforms'/name).read_text(encoding='utf-8'))
            new=timed_scene(old); before=copy.deepcopy(new)
            self.assertEqual(compile_scene(old,CATALOG),compile_scene(new,CATALOG))
            self.assertEqual(new,before)

    def test_all_catalog_variants_keep_their_default_output(self):
        for entry in CATALOG['modes']:
            if entry['mode']>23: continue
            for case in entry['cases']:
                for signal in ('vin','gate'):
                    b=dict(channel=1,topology=entry['topology'],mode=entry['mode'],signal=signal,
                           variant=case['variant'],frequency_hz=100000)
                    old={'channels':[b]}
                    with self.subTest(topology=entry['topology'],mode=entry['mode'],variant=case['variant'],signal=signal):
                        self.assertEqual(compile_scene(old,CATALOG)['packets'],compile_scene(timed_scene(old),CATALOG)['packets'])

    def test_internal_period_and_duty_are_actual_times(self):
        for mode in (11,12):
            for duration in (50,100):
                b=binding(mode,parameters={'vin_period_us':2,'vin_duty_percent':25,'pulse_count':4})
                b['duration_us']=duration
                wave,_,_=make_waveform(CATALOG,b)
                scale=duration/wave.period_us
                pulses=[(wave.points[i][0]*scale,wave.points[i+3][0]*scale) for i in range(1,len(wave.points)-1,4)]
                self.assertEqual(len(pulses),4)
                for start,end in pulses: self.assertAlmostEqual(end-start,.5)
                for a,z in zip(pulses,pulses[1:]): self.assertAlmostEqual(z[0]-a[1],1.5)

    def test_legacy_internal_period_migration_preserves_output(self):
        for mode in (11,12):
            params={'vin_frequency_khz':500,'vin_duty_percent':25,'pulse_count':4}
            if mode==11: params['gate_frequency_khz']=700
            old={'channels':[dict(channel=n,topology=6,mode=mode,signal=signal,frequency_hz=20000,
                                  parameters=params,pair='A') for n,signal in ((1,'vin'),(2,'gate'))]}
            self.assertEqual(compile_scene(old,CATALOG)['packets'],compile_scene(timed_scene(old),CATALOG)['packets'])

    def test_nonterminating_reciprocals_keep_exact_common_period(self):
        scene={'channels':[dict(channel=n,topology=6,mode=1,signal='vin',duration_us=t)
                           for n,t in ((1,7),(2,14))]}
        plan=compile_scene(scene,CATALOG)
        self.assertAlmostEqual(plan['pattern_duration_us'],14)
        self.assertEqual(plan['channels'][0]['cycles_per_frame'],2)
        self.assertEqual(plan['channels'][1]['cycles_per_frame'],1)
        gate=binding(11,'gate',parameters={'gate_period_us':1000/700})
        wave,_,_=make_waveform(CATALOG,gate)
        self.assertEqual(wave.continuity_multiple,1)

    def test_preview_shows_actual_period_and_time_error(self):
        old=json.loads((ROOT/'waveforms/example_basic_1khz.json').read_text())
        result=public_preview(timed_scene(old),CATALOG)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['summary']['frame_duration_us'],1000)
        errors=[]
        for row in result['channels']:
            self.assertAlmostEqual(row['period_us'],1e6/row['frequency_hz'])
            errors.append(abs(row['period_us']-1000))
        self.assertAlmostEqual(result['summary']['max_duration_error_us'],max(errors))
        gate=binding(11,'gate',parameters={'gate_period_us':2},pair='missing')
        fallback=public_preview({'channels':[gate]},CATALOG)
        self.assertFalse(fallback['ok'])
        self.assertEqual(fallback['channels'][0]['duration_us'],50)
        self.assertAlmostEqual(fallback['channels'][0]['carrier_period_us'],2)

    def test_invalid_and_conflicting_durations_are_rejected(self):
        for value in (0,-1,float('nan'),float('inf'),True,'bad'):
            for key in ('duration_us','vin_period_us','gate_period_us'):
                b=binding()
                if key=='duration_us': b[key]=value
                else: b['parameters']={key:value}
                with self.subTest(key=key,value=value),self.assertRaises((ValueError,TypeError)):
                    compile_scene({'channels':[b]},CATALOG)
        with self.assertRaisesRegex(ValueError,'不一致'):
            binding_frequency(binding(frequency_hz=100000))
        for params in ({'vin_period_us':2,'vin_frequency_khz':500},
                       {'gate_period_us':2,'gate_sine_period_us':2},
                       {'vin_period_us':2,'pulse_gap_us':1}):
            with self.assertRaises(ValueError): make_waveform(CATALOG,binding(parameters=params))

    def test_static_scan_and_pair_validation_use_duration(self):
        b=binding(24,parameters={'period_us':1000,'start_us':10,'width_us':10})
        b['duration_us']=1000
        result=public_preview({'channels':[b]},CATALOG)
        self.assertTrue(result['ok'])
        self.assertEqual(result['channels'][0]['duration_us'],1000)
        self.assertGreater(result['channels'][0]['zero_tail_us'],979)
        scene={'channels':[dict(channel=n,mode=1,topology=6,signal=signal,duration_us=t,pair='A')
                           for n,signal,t in ((1,'vin',10),(2,'gate',20))]}
        plan=compile_scene(scene,CATALOG)
        self.assertEqual(plan['channels'][1]['source'],'constant')
        self.assertAlmostEqual(plan['pattern_duration_us'],10)
        scene['channels'][1].pop('duration_us');scene['channels'][1]['frequency_hz']=100000
        self.assertTrue(public_preview(scene,CATALOG)['ok'])


if __name__=='__main__': unittest.main()
