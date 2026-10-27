"""Channel-local controls, DC semantics and identical sampling policy."""
import copy
import unittest

from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_waveforms import make_waveform
from firing_web import public_preview

CATALOG=load_catalog()


def channel(number,mode,signal,**kw):
    return dict(channel=number,mode=mode,signal=signal,topology=6,pair='A',**kw)


class IndependentTests(unittest.TestCase):
    def test_separate_edges_and_widths_do_not_change_peer_wave(self):
        a=channel(1,3,'vin',duration_us=20,parameters={'vin_width_us':4,'rise_time_us':.2,'fall_time_us':.3})
        b=channel(2,3,'gate',duration_us=20,parameters={'gate_width_us':.6,'pulse_gap_us':.4,
            'pulse_count':4,'rise_time_us':.1,'fall_time_us':.1})
        scene={'channels':[a,b]}; original=copy.deepcopy(scene)
        first=compile_scene(scene,CATALOG)
        self.assertEqual(scene,original)
        b['parameters']['rise_time_us']=.15
        second=compile_scene(scene,CATALOG)
        self.assertEqual(first['hold'],second['hold'])
        self.assertEqual(first['channels'][0]['samples'],second['channels'][0]['samples'])
        self.assertNotEqual(first['channels'][1]['samples'],second['channels'][1]['samples'])

    def test_edges_are_actual_us_and_are_not_silently_clipped(self):
        for duration in (20,40):
            b=channel(1,3,'vin',duration_us=duration,
                parameters={'vin_width_us':4,'rise_time_us':.2,'fall_time_us':.3})
            wave,_,_=make_waveform(CATALOG,b)
            p=wave.points; scale=duration/wave.period_us
            self.assertAlmostEqual((p[2][0]-p[1][0])*scale,.2)
            self.assertAlmostEqual((p[4][0]-p[3][0])*scale,.3)
            b['parameters']['rise_time_us']=4
            with self.assertRaisesRegex(ValueError,'之和不能超过脉宽'):
                make_waveform(CATALOG,b)

    def test_paired_dynamic_durations_and_phases_are_independent(self):
        scene={'channels':[channel(1,3,'vin',duration_us=10),channel(2,3,'gate',duration_us=20,phase_deg=35)]}
        plan=compile_scene(scene,CATALOG)
        self.assertAlmostEqual(plan['pattern_duration_us'],20)
        self.assertEqual([c['cycles_per_frame'] for c in plan['channels'][:2]],[2,1])
        scene['channels'][1]['mode']=4
        with self.assertRaisesRegex(ValueError,'模式'): compile_scene(scene,CATALOG)

    def test_touching_edges_do_not_create_a_floating_point_plateau(self):
        for rise,fall in ((.1,.2),(.2,.1),(.15,.15)):
            b=channel(1,1,'vin',duration_us=20,parameters={
                'vin_width_us':.3,'rise_time_us':rise,'fall_time_us':fall})
            b.pop('pair')
            wave,_,_=make_waveform(CATALOG,b)
            self.assertEqual(wave.points[2][0],wave.points[3][0])
            self.assertEqual(compile_scene({'channels':[b]},CATALOG)['channels'][0]['source'],'sram')

    def test_dc_has_no_timing_and_leaves_memory_for_dynamic_channel(self):
        scene={'channels':[channel(1,12,'vin',duration_us=400),
            channel(2,12,'gate',amplitude_v=6.2,phase_deg='irrelevant',
                    parameters={'vin_period_us':-1,'pulse_count':0,'rise_us':-10})]}
        result=public_preview(scene,CATALOG)
        self.assertTrue(result['ok'],result.get('error'))
        gate=result['channels'][1]
        self.assertEqual(gate['source'],'constant');self.assertEqual(gate['sram_words'],0)
        self.assertGreater(result['channels'][0]['sram_words'],2048)
        self.assertEqual(gate['period_us'],None)

    def test_resonance_anchor_comes_from_vin_not_gate_copied_parameters(self):
        scene={'channels':[channel(1,11,'vin',duration_us=50,parameters={
            'start_us':17,'vin_period_us':2,'vin_duty_percent':30,'pulse_count':3}),
            channel(2,11,'gate',duration_us=100,parameters={'gate_period_us':2})]}
        vin,_,_=make_waveform(CATALOG,scene['channels'][0])
        center=(vin.points[1][0]+vin.points[4][0])/2/vin.period_us*50
        plan=compile_scene(scene,CATALOG); samples=plan['channels'][1]['samples'];step=plan['sample_interval_us']
        for t in (center,center+2,center+4):
            i=round(t/step)
            self.assertGreaterEqual(samples[i],max(samples[i-2:i+3])-1)
        # A deliberately impossible third channel must not change the relative
        # phase shown by the theoretical fallback preview.
        scene['channels'].append(dict(channel=3,mode=3,topology=6,signal='vin',duration_us=10000))
        fallback=public_preview(scene,CATALOG)
        self.assertFalse(fallback['ok'])
        gate=fallback['channels'][1];i=round(center/gate['step_us'])
        self.assertGreaterEqual(gate['samples'][i],max(gate['samples'][i-1:i+2])-1e-9)

    def test_full_and_compact_sampling_reject_same_subsample_plateau(self):
        scene={'channels':[dict(channel=1,mode=24,topology=6,signal='vin',duration_us=100,
            parameters={'period_us':100,'start_us':10,'width_us':.001,'rise_time_us':0,'fall_time_us':0})]}
        for compact in (False,True):
            with self.assertRaisesRegex(ValueError,'不足一个 DAC 采样间隔'):
                compile_scene(scene,CATALOG,_compact=compact)
        scene['channels'][0]['duration_us']=20
        scene['channels'][0]['parameters'].update(period_us=20,start_us=2,width_us=4)
        full=compile_scene(scene,CATALOG)
        compact=compile_scene(scene,CATALOG,_compact=True)
        a,b=full['channels'][0],compact['channels'][0]
        self.assertEqual(full['hold'],compact['hold'])
        self.assertEqual(a['samples'],b['samples']+[0]*b['zero_tail_samples'])
        self.assertEqual(a['sampling_warnings'],b['sampling_warnings'])


if __name__=='__main__': unittest.main()
