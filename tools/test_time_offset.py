"""Physical-time offsets, sign, migration and standard-waveform event timing."""
import unittest

from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_waveforms import binding_time_offset
from firing_web import public_preview

CATALOG=load_catalog()


def binding(mode=1,**kw):
    return dict(channel=1,topology=6,mode=mode,signal='vin',duration_us=20,**kw)


class TimeOffsetTests(unittest.TestCase):
    def test_signed_delay_is_in_us_independent_of_window(self):
        for duration in (20,40):
            base=binding(parameters={'vin_width_us':4,'rise_time_us':0,'fall_time_us':0})
            base['duration_us']=duration
            before=compile_scene({'channels':[base]},CATALOG)
            first=next(i for i,v in enumerate(before['channels'][0]['samples']) if v>0)
            for delay in (-.2,.2):
                shifted=dict(base,time_offset_us=delay)
                after=compile_scene({'channels':[shifted]},CATALOG)
                self.assertEqual(before['hold'],after['hold'])
                edge=next(i for i,v in enumerate(after['channels'][0]['samples']) if v>0)
                self.assertAlmostEqual((edge-first)*after['sample_interval_us'],delay,delta=after['sample_interval_us'])

    def test_legacy_angle_migrates_with_opposite_sign(self):
        old=binding(phase_deg=90)
        self.assertEqual(binding_time_offset(old),-5)
        new=dict(old);new.pop('phase_deg');new['time_offset_us']=-5
        self.assertEqual(compile_scene({'channels':[old]},CATALOG)['packets'],compile_scene({'channels':[new]},CATALOG)['packets'])

    def test_resonator_delay_and_fallback_keep_same_direction(self):
        params={'vin_period_us':2,'vin_duty_percent':50,'pulse_count':4}
        vin=binding(11,pair='A',parameters=params);vin['duration_us']=40
        gate=dict(channel=2,topology=6,mode=11,signal='gate',duration_us=40,pair='A',parameters={'gate_frequency_khz':500})
        a=compile_scene({'channels':[vin,gate]},CATALOG)
        gate['time_offset_us']=.2
        b=compile_scene({'channels':[vin,gate]},CATALOG)
        self.assertEqual(a['channels'][0]['samples'],b['channels'][0]['samples'])
        step=b['sample_interval_us'];center=40/3+.5
        peak=lambda samples: max(range(round((center-.4)/step),round((center+.6)/step)),key=lambda i:samples[i])
        self.assertAlmostEqual((peak(b['channels'][1]['samples'])-peak(a['channels'][1]['samples']))*step,.2,delta=2*step)
        bad=dict(vin,pair='missing');bad['time_offset_us']=.2
        preview=public_preview({'channels':[bad]},CATALOG)
        self.assertFalse(preview['ok']);self.assertEqual(preview['channels'][0]['time_offset_us'],.2)

    def test_native_sine_uses_actual_frequency_to_encode_delay(self):
        for frequency in (1000,2000):
            b=dict(channel=1,mode=26,topology=6,signal='vin',frequency_hz=frequency,time_offset_us=100,amplitude_v=1)
            row=compile_scene({'channels':[b]},CATALOG)['channels'][0]
            word=row['phase_word'];signed=word if word<32768 else word-65536
            delay=-signed/65535/row['frequency_hz']*1e6
            self.assertAlmostEqual(delay,100,delta=1e6/row['frequency_hz']/65535)

    def test_square_delay_changes_events_and_preview(self):
        for delay in (500,-500):
            b=dict(channel=1,mode=25,topology=6,signal='vin',duration_us=1000,time_offset_us=delay,amplitude_v=1)
            plan=compile_scene({'channels':[b]},CATALOG)
            self.assertLess(plan['channels'][0]['samples'][0],0)
            self.assertGreater(plan['channels'][0]['samples'][750],0)
            events=plan['basic_events']
            # DAC1 code is event word 5; starts low, rises 500 us later.
            self.assertGreater(events[0]['words'][5],0x8000)
            self.assertLess(events[1]['words'][5],0x8000)
            self.assertEqual(events[1]['ticks']-events[0]['ticks'],50000)
        b['time_offset_us']=100
        with self.assertRaisesRegex(ValueError,'切换过密'): compile_scene({'channels':[b]},CATALOG)

    def test_bad_offsets_and_conflicting_legacy_fields_are_rejected(self):
        for value in (float('nan'),float('inf'),True,'bad'):
            with self.assertRaisesRegex(ValueError,'时间偏移'): compile_scene({'channels':[binding(time_offset_us=value)]},CATALOG)
        with self.assertRaisesRegex(ValueError,'旧相位字段不一致'):
            compile_scene({'channels':[binding(time_offset_us=1,phase_deg=90)]},CATALOG)


if __name__=='__main__': unittest.main()
