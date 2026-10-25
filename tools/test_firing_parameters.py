"""Independent widths, off-times and three-level voltage controls."""
import copy
import json
import unittest

from ad9106_firing import compile_scene
from firing_waveforms import make_waveform
from firing_gui_core import load_catalog
from firing_web import public_preview

CATALOG=load_catalog()


def binding(mode,signal="vin",**values):
    b=dict(channel=1,topology=6,mode=mode,signal=signal,frequency_hz=100000)
    b.update(values)
    return b


def pulse_times(b):
    w,_,_=make_waveform(CATALOG,b)
    factor=w.period_us*b["frequency_hz"]/1e6
    # train() emits four points per pulse between its start/end sentinels.
    return [(w.points[i][0]/factor,w.points[i+3][0]/factor) for i in range(1,len(w.points)-1,4)]


class ParameterTests(unittest.TestCase):
    def test_mode3_gate_on_time_and_off_time_are_independent(self):
        b=binding(3,"gate",parameters={"gate_width_us":1.0,"pulse_gap_us":.5})
        first=pulse_times(b)
        self.assertEqual(len(first),3)
        for a,z in first:self.assertAlmostEqual(z-a,1)
        for a,z in zip(first,first[1:]):self.assertAlmostEqual(z[0]-a[1],.5)
        b["parameters"]["gate_width_us"]=1.5
        second=pulse_times(b)
        for a,z in second:self.assertAlmostEqual(z-a,1.5)
        for a,z in zip(second,second[1:]):self.assertAlmostEqual(z[0]-a[1],.5)

    def test_mode20_negative_pulses_keep_independent_gap(self):
        b=binding(20,parameters={"vin_width_us":.8,"pulse_gap_us":.7})
        w,_,_=make_waveform(CATALOG,b)
        self.assertLess(min(v for _,v in w.points),0)
        p=pulse_times(b)
        for a,z in p:self.assertAlmostEqual(z-a,.8)
        for a,z in zip(p,p[1:]):self.assertAlmostEqual(z[0]-a[1],.7)

    def test_integrator_vin_width_and_gap_with_constant_gate(self):
        for variant in (0,1):
            b=binding(12,variant=variant,frequency_hz=10000,
                      parameters={"vin_width_us":.7,"pulse_gap_us":1.3})
            p=pulse_times(b)
            self.assertAlmostEqual(p[0][1]-p[0][0],.7)
            self.assertEqual(len(p),6)
            self.assertAlmostEqual(p[1][0]-p[0][1],1.3)
            for variant in (0,1):
                gate={**b,"channel":2,"signal":"gate","variant":variant,"amplitude_v":4.2}
                wave,_,_=make_waveform(CATALOG,gate)
                self.assertEqual(wave.constant,7.1)
                plan=compile_scene({"channels":[gate]},CATALOG)
                row=plan["channels"][1]
                self.assertEqual(row["source"],"constant")
                self.assertAlmostEqual(row["nominal_min_v"],4.2,delta=.005)

    def test_mode11_frequency_does_not_change_width_or_gate(self):
        b=binding(11,frequency_hz=1e6/60,parameters={"vin_width_us":.5,"vin_frequency_khz":500})
        before=pulse_times(b)
        gate={**b,"signal":"gate"};g1,_,_=make_waveform(CATALOG,gate)
        b["parameters"]["vin_frequency_khz"]=1000
        after=pulse_times(b);g2,_,_=make_waveform(CATALOG,gate)
        self.assertAlmostEqual(before[1][0]-before[0][0],2)
        self.assertAlmostEqual(after[1][0]-after[0][0],1)
        for a,z in before+after:self.assertAlmostEqual(z-a,.5)
        self.assertEqual(g1.sine_period_us,g2.sine_period_us)
        self.assertEqual([g1.value(i/60) for i in range(60)],[g2.value(i/60) for i in range(60)])

    def test_mode15_three_levels_are_direct_voltages(self):
        params={"level_low_v":2,"level_mid_v":4,"level_high_v":6,"gate_width_us":.5,"vin_width_us":1}
        for part,expected in (("low",2),("mid",4),("high",6)):
            b=binding(15,"gate",component=part,parameters=params,amplitude_v=9)
            plan=compile_scene({"channels":[b]},CATALOG)
            self.assertAlmostEqual(plan["channels"][0]["nominal_max_v"],expected,delta=.005)
        b=binding(15,"gate",parameters=params,amplitude_v=9)
        plan=compile_scene({"channels":[b]},CATALOG)
        codes=set(plan["memory"])
        for v in (2,4,6):self.assertIn(round(v*2048/10),codes)
        vin={**b,"signal":"vin"}
        self.assertAlmostEqual(pulse_times(vin)[0][1]-pulse_times(vin)[0][0],1)
        self.assertAlmostEqual(pulse_times(b)[0][1]-pulse_times(b)[0][0],.5)
        preview=public_preview({"channels":[{**b,"pair":"incomplete"}]},CATALOG)
        self.assertFalse(preview["ok"])
        self.assertAlmostEqual(max(preview["channels"][0]["samples"]),6)

    def test_width_and_gap_remain_actual_us_under_envelope_change(self):
        for frequency in (50000,100000):
            b=binding(3,"gate",frequency_hz=frequency,parameters={"gate_width_us":.5,"pulse_gap_us":.4})
            p=pulse_times(b)
            self.assertAlmostEqual(p[0][1]-p[0][0],.5)
            self.assertAlmostEqual(p[1][0]-p[0][1],.4)

    def test_mode22_gap_starts_after_pulse_returns_to_baseline(self):
        b=binding(22,parameters={"vin_width_us":.5,"pulse_gap_us":.2})
        p=pulse_times(b)
        self.assertAlmostEqual(p[0][1]-p[0][0],.5)
        self.assertAlmostEqual(p[1][0]-p[0][1],.2)

    def test_widths_reach_all_18_modes(self):
        modes=(1,2,3,4,5,6,7,9,11,12,15,16,18,19,20,21,22,23)
        for mode in modes:
            requested=.05 if mode in (11,12) else 1
            b=binding(mode,parameters={"vin_width_us":requested,"ramp_us":.1})
            with self.subTest(mode=mode):
                w,_,_=make_waveform(CATALOG,b)
                if mode in (7,18,23):
                    factor=w.period_us*b["frequency_hz"]/1e6
                    end=w.points[-3][0]
                    self.assertAlmostEqual((end-w.points[1][0])/factor,1)
                else:
                    a,z=pulse_times(b)[0];self.assertAlmostEqual(z-a,requested)

    def test_pair_compile_roundtrip_and_invalid_values(self):
        params={"vin_width_us":3,"gate_width_us":1,"pulse_gap_us":.5}
        scene={"channels":[binding(3,s,channel=n,pair="A",parameters=copy.deepcopy(params)) for n,s in ((1,"vin"),(2,"gate"))]}
        old=json.dumps(scene,sort_keys=True)
        plan=compile_scene(scene,CATALOG)
        self.assertEqual(old,json.dumps(scene,sort_keys=True))
        self.assertEqual(plan,compile_scene(json.loads(old),CATALOG))
        for params in ({"vin_width_us":0},{"vin_width_us":-1},{"pulse_gap_us":-1},
                       {"vin_width_us":float("nan")},{"pulse_count":1.5},{"vin_width_us":1000}):
            with self.subTest(params=params),self.assertRaises(ValueError):
                make_waveform(CATALOG,binding(20,parameters=params))
        with self.assertRaises(ValueError):
            make_waveform(CATALOG,binding(15,"gate",parameters={"level_low_v":11}))

    def test_two_stages_have_independent_voltage_and_duration(self):
        for mode,signal,topology in ((5,"gate",6),(5,"gate",7),(7,"vin",6)):
            params={"stage1_voltage_v":3,"stage2_voltage_v":5,"first_stage_us":1.2,"second_stage_us":2.3}
            b=binding(mode,signal,topology=topology,parameters=params,amplitude_v=9)
            w,_,_=make_waveform(CATALOG,b); factor=w.period_us*b["frequency_hz"]/1e6
            start=20/factor
            self.assertAlmostEqual(w.value((start+1.2+1)*b["frequency_hz"]/1e6),5)
            self.assertAlmostEqual(w.points[-3][0]/factor-start,3.5)
            if mode==7:self.assertAlmostEqual(w.value((start+.6)*b["frequency_hz"]/1e6),1.5)
            elif topology==7:self.assertAlmostEqual(w.value((start+.6)*b["frequency_hz"]/1e6),3)
            else:self.assertTrue(3<w.value((start+.6)*b["frequency_hz"]/1e6)<5)
            plan=compile_scene({"channels":[b]},CATALOG)
            self.assertAlmostEqual(plan["channels"][0]["nominal_max_v"],5,delta=.005)
            params["first_stage_us"]=.8
            changed,_,_=make_waveform(CATALOG,b)
            self.assertAlmostEqual((changed.points[-3][0]-changed.points[-4][0])/factor,2.3)

    def test_mode6_ramp_endpoints_are_absolute_voltages(self):
        b=binding(6,"gate",amplitude_v=9,parameters={"gate_initial_v":6,"gate_final_v":2,"gate_width_us":3})
        wave,_,_=make_waveform(CATALOG,b)
        self.assertEqual(wave.points[2][1],6)
        self.assertEqual(wave.points[3][1],2)
        self.assertAlmostEqual((wave.points[3][0]-wave.points[1][0])/22,3)
        plan=compile_scene({"channels":[b]},CATALOG)
        # A sampled ramp can miss its exact endpoint by one sampling interval.
        self.assertAlmostEqual(plan["channels"][0]["nominal_max_v"],6,delta=.02)

    def test_mode3_gate_count_and_pair_compile(self):
        params={"pulse_count":5,"gate_width_us":.5,"pulse_gap_us":.3}
        self.assertEqual(len(pulse_times(binding(3,"gate",parameters=params))),5)
        scene={"channels":[binding(3,s,channel=n,pair="A",parameters=params) for n,s in ((1,"vin"),(2,"gate"))]}
        self.assertTrue(public_preview(scene,CATALOG)["ok"])

    def test_internal_frequency_duty_and_separate_integrator_variants(self):
        for mode in (11,12):
            for envelope in (10000,20000):
                b=binding(mode,frequency_hz=envelope,parameters={"vin_frequency_khz":500,"vin_duty_percent":25,"pulse_count":4})
                pulses=pulse_times(b)
                self.assertEqual(len(pulses),4)
                for start,end in pulses:self.assertAlmostEqual(end-start,.5)
                for a,z in zip(pulses,pulses[1:]):self.assertAlmostEqual(z[0]-a[0],2)
        fast=pulse_times(binding(12,variant=0))
        slow=pulse_times(binding(12,variant=1))
        self.assertEqual(len(fast),6);self.assertEqual(len(slow),6)
        self.assertGreater(slow[1][0]-slow[0][0],fast[1][0]-fast[0][0])
        self.assertAlmostEqual(fast[0][0],slow[0][0])
        for params in ({"vin_duty_percent":0},{"vin_duty_percent":100},{"vin_frequency_khz":0},{"second_stage_us":-1}):
            with self.subTest(params=params),self.assertRaises(ValueError):make_waveform(CATALOG,binding(12,parameters=params))

    def test_resonator_gate_sine_frequency_is_independent_and_exact(self):
        for topology in (3,5,6,7):
            b=binding(11,"gate",topology=topology,parameters={"gate_frequency_khz":700})
            w,_,_=make_waveform(CATALOG,b)
            factor=w.period_us*b["frequency_hz"]/1e6
            self.assertAlmostEqual(w.sine_period_us/factor,1000/700)
            self.assertEqual(w.continuity_multiple,1)
            self.assertIsNotNone(w.analytic)
            plan=compile_scene({"channels":[b]},CATALOG)
            self.assertAlmostEqual(plan["channels"][0]["sine_carrier_hz"],700000)

    def test_current_catalog_every_variant_compiles(self):
        for entry in CATALOG["modes"]:
            if entry["mode"]>23:continue
            for case in entry["cases"]:
                for signal in ("vin","gate"):
                    for part in entry["components"]:
                        b=binding(entry["mode"],signal,topology=entry["topology"],variant=case["variant"],component=part)
                        with self.subTest(binding=b):compile_scene({"channels":[b]},CATALOG)


if __name__=="__main__":unittest.main(verbosity=2)
