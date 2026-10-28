"""Independent rhythm carriers, physical sample timing and finite playback."""
import copy
import json
import math
import unittest

from ad9106_firing import compile_scene, voltage_code
from firing_gui_core import load_catalog
from firing_web import public_preview
from firing_waveforms import make_waveform

CATALOG=load_catalog()


def scene(kind='square_sine',gate_frequency=25000,phase=0,window=200):
    return dict(rhythm_modulation={'duration_us':window},repeat_count=1,interval_s=.01,channels=[
        dict(channel=1,mode=25,topology=6,signal='vin',pair='A',frequency_hz=25000,
             phase_deg=0,amplitude_v=.5,offset_v=.5,parameters={'duty_percent':50}),
        dict(channel=2,mode=26 if kind=='square_sine' else 25,topology=6,signal='gate',pair='A',
             frequency_hz=gate_frequency,phase_deg=phase,amplitude_v=.5,offset_v=.5,
             parameters={} if kind=='square_sine' else {'duty_percent':50})])


class RhythmTests(unittest.TestCase):
    def integrated_scene(self,mode=27):
        return dict(repeat_count=1,interval_s=.01,channels=[
            dict(channel=1,mode=mode,topology=6,signal='vin',pair='A',duration_us=200,
                 amplitude_v=.5,offset_v=.5,parameters={'rhythm_on_us':20,'rhythm_duty_percent':50,'rhythm_phase_deg':0}),
            dict(channel=2,mode=mode,topology=6,signal='gate',pair='A',duration_us=200,
                 amplitude_v=.5,offset_v=.5,parameters={'rhythm_frequency_khz':26,'rhythm_phase_deg':90,
                     **({'rhythm_duty_percent':50} if mode==28 else {})})])

    def test_integrated_modes_match_carrier_samples(self):
        for mode,kind in ((27,'square_sine'),(28,'square_square')):
            config=self.integrated_scene(mode);original=copy.deepcopy(config)
            plan=compile_scene(config,CATALOG)
            old=compile_scene(scene(kind,gate_frequency=26000,phase=90),CATALOG)
            self.assertEqual(config,original)
            self.assertEqual(plan['packets'],old['packets'])
            self.assertEqual([c['mode'] for c in plan['channels'][:2]],[mode,mode])
            self.assertEqual(plan['channels'][1]['waveform'],'sine' if mode==27 else 'square')
            self.assertTrue(public_preview(config,CATALOG)['ok'])

    def test_mode27_vin_edges_preserve_on_time_frequency_and_gate(self):
        config=self.integrated_scene(27);baseline=compile_scene(config,CATALOG)
        config['channels'][0]['parameters'].update(rise_time_us=.4,fall_time_us=.6)
        plan=compile_scene(config,CATALOG)
        self.assertEqual(plan['rhythm_modulation'],baseline['rhythm_modulation'])
        self.assertEqual(plan['channels'][1]['samples'],baseline['channels'][1]['samples'])
        self.assertEqual((plan['channels'][0]['rise_time_us'],plan['channels'][0]['fall_time_us']),(.4,.6))
        wave,_,_=make_waveform(CATALOG,config['channels'][0])
        for time,expected in ((0,-1),(.2,0),(.4,1),(5,1),(19.4,1),(19.7,0),(20,-1),(40.2,0)):
            self.assertAlmostEqual(wave.value(time/200),expected,places=9)
        row=plan['channels'][0];step=plan['sample_interval_us']
        for i,code in enumerate(row['samples'][:4]):
            self.assertAlmostEqual(code,voltage_code(i*step/.4,10,0),delta=1)
        self.assertEqual(row['samples'][-1],0)

    def test_mode28_edges_are_independent_for_both_channels(self):
        config=self.integrated_scene(28)
        config['channels'][0]['parameters'].update(rise_time_us=.3,fall_time_us=.7)
        config['channels'][1]['parameters'].update(rise_time_us=.8,fall_time_us=.2,rhythm_phase_deg=0)
        plan=compile_scene(config,CATALOG)
        for b,rise,fall,period in ((config['channels'][0],.3,.7,40),(config['channels'][1],.8,.2,1e6/26000)):
            wave,_,_=make_waveform(CATALOG,b)
            for time,expected in ((rise/2,0),(rise,1),(period/2-fall/2,0),(period/2,-1),(period+rise/2,0)):
                self.assertAlmostEqual(wave.value(time/200),expected,places=9)
        self.assertNotEqual(plan['channels'][0]['samples'],plan['channels'][1]['samples'])
        result=public_preview(config,CATALOG)
        self.assertTrue(result['ok'])
        self.assertEqual((result['channels'][1]['rise_time_us'],result['channels'][1]['fall_time_us']),(.8,.2))

    def test_rhythm_edge_zero_and_one_boundaries(self):
        for mode in (27,28):
            config=self.integrated_scene(mode);baseline=compile_scene(config,CATALOG)
            squares=[b for b in config['channels'] if b['signal']=='vin' or mode==28]
            for b in squares:b['parameters'].update(rise_time_us=0,fall_time_us=0)
            self.assertEqual(compile_scene(config,CATALOG)['packets'],baseline['packets'])
            for b in squares:b['parameters'].update(rise_time_us=1,fall_time_us=1)
            plan=compile_scene(config,CATALOG)
            self.assertEqual(plan['hardware_pattern_repeats'],1)
            for b in squares:
                row=plan['channels'][b['channel']-1]
                self.assertGreater(len(set(row['samples'])),2)
                self.assertEqual(row['sampling_warnings'],[])

    def test_rhythm_invalid_edges_and_oversized_edges_are_rejected(self):
        for mode in (27,28):
            for key in ('rise_time_us','fall_time_us'):
                for value in (-.01,1.01,True,None,float('nan'),float('inf')):
                    config=self.integrated_scene(mode)
                    config['channels'][0]['parameters'][key]=value
                    with self.subTest(mode=mode,key=key,value=value),self.assertRaisesRegex(ValueError,'0～1 μs'):
                        compile_scene(config,CATALOG)
                    self.assertFalse(public_preview(config,CATALOG)['ok'])
        config=self.integrated_scene(28)
        config['channels'][0]['parameters'].update(rhythm_on_us=.5,rise_time_us=.3,fall_time_us=.3)
        with self.assertRaisesRegex(ValueError,'超过方波 ON 时间'):compile_scene(config,CATALOG)
        config=self.integrated_scene(28)
        config['channels'][1]['parameters'].update(rhythm_frequency_khz=1000,rise_time_us=.3,fall_time_us=.3)
        with self.assertRaisesRegex(ValueError,'超过方波 ON 时间'):compile_scene(config,CATALOG)

    def test_subsample_rhythm_edges_warn_and_sine_rejects_edge_parameters(self):
        config=self.integrated_scene(27)
        config['channels'][0]['parameters'].update(rise_time_us=.001,fall_time_us=.002)
        result=public_preview(config,CATALOG)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['channels'][0]['sampling_warnings']),2)
        self.assertTrue(all('小于采样间隔' in warning for warning in result['channels'][0]['sampling_warnings']))
        config['channels'][1]['parameters']['rise_time_us']=.5
        with self.assertRaisesRegex(ValueError,'不适用'):compile_scene(config,CATALOG)

    def test_integrated_preview_parameters_and_phase_drift(self):
        config=self.integrated_scene()
        config['channels'][0]['parameters']['rhythm_on_us']=16
        config['channels'][1]['parameters']['rhythm_phase_deg']=-90
        result=public_preview(config,CATALOG)
        info=result['summary']['rhythm_modulation']
        self.assertEqual(info['vin_frequency_hz'],31250)
        self.assertEqual(info['gate_frequency_hz'],26000)
        self.assertEqual(info['initial_phase_difference_deg'],-90)
        self.assertEqual(info['phase_drift_deg'],-378)

    def test_integrated_mode_validation_and_fallback_preview(self):
        for change in ('mode','window','on','phase','duty','unknown','capacity'):
            config=self.integrated_scene()
            if change=='mode':config['channels'][1]['mode']=28
            if change=='window':config['channels'][1]['duration_us']=100
            if change=='on':config['channels'][0]['parameters']['rhythm_on_us']=0
            if change=='phase':config['channels'][0]['parameters']['rhythm_phase_deg']=float('inf')
            if change=='duty':config['channels'][0]['parameters']['rhythm_duty_percent']=100
            if change=='unknown':config['channels'][0]['parameters']['vin_width_us']=20
            if change=='capacity':
                for b in config['channels']:b['duration_us']=1000
            with self.subTest(change=change),self.assertRaises(ValueError):compile_scene(config,CATALOG)
            preview=public_preview(config,CATALOG)
            self.assertFalse(preview['ok'])
            if change=='capacity':
                self.assertEqual(preview['channels'][0]['frequency_hz'],25000)
                self.assertEqual(preview['channels'][1]['frequency_hz'],26000)
                self.assertEqual(preview['channels'][1]['waveform'],'sine')

    def test_defaults_on_20us_and_single_observation_window(self):
        config=scene();original=copy.deepcopy(config);plan=compile_scene(config,CATALOG)
        self.assertEqual(config,original)
        self.assertEqual(plan['hardware_pattern_repeats'],1)
        self.assertEqual(plan['rhythm_modulation']['observation_duration_us'],200)
        self.assertLessEqual(plan['sram_words'],4096)
        self.assertEqual([c['source'] for c in plan['channels']],['sram','sram','constant','constant'])
        step=plan['sample_interval_us'];vin=plan['channels'][0]['samples']
        first_fall=next(i for i,v in enumerate(vin) if v==0)
        self.assertAlmostEqual(first_fall*step,20,delta=step)
        for c in plan['channels'][:2]:self.assertEqual(c['samples'][-1],0)
        regs=dict(plan['register_and_sram_writes'])
        self.assertEqual((regs[0x1f],regs[0x2a],regs[0x2b]),(1,0,0))
        self.assertEqual(plan,compile_scene(json.loads(json.dumps(config)),CATALOG))

    def test_sine_phase_frequency_and_no_reset_at_vin_period_boundary(self):
        before=compile_scene(scene(),CATALOG)
        for phase in (-90,0,90,180,450):
            with self.subTest(phase=phase):
                plan=compile_scene(scene(gate_frequency=26000,phase=phase),CATALOG)
                self.assertEqual(plan['channels'][0]['samples'],before['channels'][0]['samples'])
                gate=plan['channels'][1]['samples'];step=plan['sample_interval_us']
                for t in (0,10,40,80,120,199):
                    i=round(t/step);seconds=i*step/1e6
                    expected=voltage_code(.5+.5*math.sin(2*math.pi*(26000*seconds+phase/360)),10,0)
                    self.assertAlmostEqual(gate[i],expected,delta=1)
                info=plan['rhythm_modulation']
                self.assertEqual(info['frequency_difference_hz'],1000)
                self.assertEqual(info['phase_drift_deg'],72)
                self.assertEqual(info['beat_period_us'],1000)

    def test_square_square_phase_and_independent_frequency(self):
        plan=compile_scene(scene('square_square',phase=90),CATALOG)
        step=plan['sample_interval_us']
        falls=[next(i for i,v in enumerate(c['samples']) if v==0)*step for c in plan['channels'][:2]]
        self.assertAlmostEqual(falls[0]-falls[1],10,delta=step)
        plan=compile_scene(scene('square_square',gate_frequency=27500,phase=-45),CATALOG)
        values=plan['channels'][1]['samples'];step=plan['sample_interval_us']
        rises=[i*step for i in range(1,len(values)-1) if values[i]>values[i-1]]
        self.assertGreater(len(rises),3)
        for a,b in zip(rises,rises[1:]):self.assertAlmostEqual(b-a,1e6/27500,delta=step)
        self.assertEqual(plan['rhythm_modulation']['phase_drift_deg'],180)

    def test_small_detuning_does_not_require_common_superperiod(self):
        for kind in ('square_sine','square_square'):
            plan=compile_scene(scene(kind,gate_frequency=25001),CATALOG)
            self.assertEqual(plan['rhythm_modulation']['frequency_difference_hz'],1)
            self.assertAlmostEqual(plan['rhythm_modulation']['phase_drift_deg'],.072)
            self.assertTrue(public_preview(scene(kind,gate_frequency=25001),CATALOG)['ok'])

    def test_identical_square_samples_share_storage(self):
        plan=compile_scene(scene('square_square'),CATALOG)
        self.assertEqual(plan['channels'][0]['shared_with'],[2])
        self.assertEqual(plan['sram_words'],len(plan['channels'][0]['samples']))
        self.assertEqual(plan['channels'][0]['start'],plan['channels'][1]['start'])

    def test_invalid_requests_and_capacity_rejected_without_mutation(self):
        for value in (0,-1,True,float('nan'),float('inf')):
            config=scene(window=value)
            with self.subTest(window=value),self.assertRaises(ValueError):compile_scene(config,CATALOG)
        for change in ('extra','vin_sine','pair','voltage','duty','short_window','sram','resolution','static'):
            config=scene()
            if change=='extra':config['channels'].append(dict(config['channels'][0],channel=3))
            if change=='vin_sine':config['channels'][0].update(mode=26,parameters={})
            if change=='pair':config['channels'][1]['pair']='B'
            if change=='voltage':config['channels'][0]['amplitude_v']=11
            if change=='duty':config['channels'][0]['parameters']['duty_percent']=0
            if change=='short_window':config['rhythm_modulation']['duration_us']=1
            if change=='sram':config['rhythm_modulation']['duration_us']=1000
            if change=='resolution':config['channels'][1]['frequency_hz']=100000000
            if change=='static':config['static_pulse']=True
            before=copy.deepcopy(config)
            with self.subTest(change=change),self.assertRaises(ValueError):compile_scene(config,CATALOG)
            self.assertEqual(config,before)
            self.assertFalse(public_preview(config,CATALOG)['ok'])

    def test_delay_and_legacy_phase_encode_same_waveform(self):
        old=scene(phase=90);new=copy.deepcopy(old)
        for b in new['channels']:
            b['time_offset_us']=-b.pop('phase_deg')/360/b['frequency_hz']*1e6
        self.assertEqual(compile_scene(old,CATALOG)['packets'],compile_scene(new,CATALOG)['packets'])


if __name__=='__main__':unittest.main(verbosity=2)
