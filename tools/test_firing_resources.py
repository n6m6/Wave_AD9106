"""Paired resonance phase and resource feedback for experimental settings."""
import unittest

from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_waveforms import make_waveform
from firing_web import public_preview

CATALOG=load_catalog()


def pair(mode=11,duration=50,parameters=None,**extra):
    return {"channels":[dict(channel=n,topology=6,mode=mode,signal=signal,
        duration_us=duration,pair="A",parameters=dict(parameters or {}),**extra)
        for n,signal in ((1,"vin"),(2,"gate"))]}


class ResourceTests(unittest.TestCase):
    def test_sine_peaks_follow_pulse_centers_and_duty(self):
        for topology in (3,5,6,7):
            for duty in (20,50,80):
                scene=pair(parameters={"vin_period_us":2,"gate_period_us":2,
                    "vin_duty_percent":duty,"pulse_count":4,"start_us":23})
                for b in scene["channels"]: b["topology"]=topology
                vin,_,_=make_waveform(CATALOG,scene["channels"][0])
                gate,_,case=make_waveform(CATALOG,scene["channels"][1])
                for i in range(1,len(vin.points)-1,4):
                    center=(vin.points[i][0]+vin.points[i+3][0])/2
                    with self.subTest(topology=topology,duty=duty,center=center):
                        self.assertAlmostEqual(gate.value(center/gate.period_us),case["gate_range_v"][1])
                        self.assertAlmostEqual(gate.value((center+gate.sine_period_us/2)/gate.period_us),0)

    def test_compiled_sine_peaks_align_with_pulses_on_sample_grid(self):
        scene=pair(parameters={"vin_period_us":2,"gate_period_us":2,
            "vin_duty_percent":30,"pulse_count":4})
        plan=compile_scene(scene,CATALOG)
        wave,_,_=make_waveform(CATALOG,scene["channels"][0])
        gate=plan["channels"][1]["samples"]
        step=plan["sample_interval_us"]
        for i in range(1,len(wave.points)-1,4):
            center=(wave.points[i][0]+wave.points[i+3][0])/2/wave.period_us*50
            index=round(center/step)
            self.assertGreaterEqual(gate[index],max(gate[index-2:index+3])-1)

    def test_unequal_periods_align_first_pulse_only(self):
        scene=pair(parameters={"vin_period_us":2,"gate_period_us":3,
            "vin_duty_percent":50,"pulse_count":4})
        vin,_,_=make_waveform(CATALOG,scene["channels"][0])
        gate,_,case=make_waveform(CATALOG,scene["channels"][1])
        center=(vin.points[1][0]+vin.points[4][0])/2
        self.assertAlmostEqual(gate.value(center/gate.period_us),case["gate_range_v"][1])
        self.assertLess(gate.value((center+2*gate.period_us/50)/gate.period_us),case["gate_range_v"][1]*.9)

    def test_dc_gate_leaves_more_than_half_sram_to_vin(self):
        for mode in (1,2,7,9,12,19,20,21,22,23):
            scene=pair(mode=mode,duration=400)
            plan=compile_scene(scene,CATALOG)
            vin,gate=plan["channels"][:2]
            with self.subTest(mode=mode):
                self.assertEqual(gate["source"],"constant")
                self.assertEqual(gate["sram_words"],0)
                self.assertGreater(vin["sram_words"],2048)
                self.assertEqual(plan["sram_words"],vin["sram_words"])
                self.assertEqual(plan["sram_free_words"],4096-plan["sram_words"])

    def test_preview_reports_shared_storage_and_fine_detail_warning(self):
        scene=pair(mode=1,duration=100)
        for b in scene["channels"]:
            b.pop("pair"); b["signal"]="vin"
        result=public_preview(scene,CATALOG)
        self.assertTrue(result["ok"])
        a,b=result["channels"][:2]
        self.assertEqual(a["shared_with"],[2]); self.assertEqual(b["shared_with"],[1])
        self.assertEqual(result["summary"]["sram_words"],a["sram_words"])
        self.assertTrue(a["sampling_warnings"])
        self.assertGreater(result["summary"]["sample_interval_us"],0)

    def test_capacity_failure_names_channels_and_required_words(self):
        result=public_preview(pair(mode=16,duration=300,offset_v=.5),CATALOG)
        self.assertFalse(result["ok"])
        for text in ("DAC1","DAC2","去重后合计","超出","点"):
            self.assertIn(text,result["error"])


if __name__=="__main__": unittest.main()
