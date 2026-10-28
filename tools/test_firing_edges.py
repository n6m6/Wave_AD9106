"""Physical edge bounds across pulse families, stage controls and static scans."""
import copy
import unittest

from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_waveforms import make_waveform, binding_frequency
from firing_web import public_preview
from test_static_pulse import scene as static_scene

CATALOG=load_catalog()


def binding(mode=1,signal="vin",**values):
    result=dict(channel=1,topology=6,mode=mode,signal=signal,duration_us=20)
    result.update(values)
    return result


def slopes(b):
    wave,_,_=make_waveform(CATALOG,b)
    factor=wave.period_us*float(binding_frequency(b))/1e6
    return [(a[1],z[1],(z[0]-a[0])/factor)
            for a,z in zip(wave.points,wave.points[1:]) if a[1]!=z[1]]


class EdgeTests(unittest.TestCase):
    def test_actual_time_and_channel_independence(self):
        for duration in (20,40):
            a=binding(3,parameters={"rise_time_us":.3,"fall_time_us":.7,"vin_width_us":2},pair="A")
            b=binding(3,"gate",channel=2,duration_us=duration,pair="A",
                      parameters={"rise_time_us":.1,"fall_time_us":.2,"gate_width_us":1})
            scene={"channels":[a,b]};original=copy.deepcopy(scene)
            self.assertTrue(public_preview(scene,CATALOG)["ok"])
            for row,rise,fall in ((a,.3,.7),(b,.1,.2)):
                for start,end,time in slopes(row):self.assertAlmostEqual(time,rise if end>start else fall)
            self.assertEqual(scene,original)

    def test_zero_and_one_microsecond_boundaries(self):
        for edge in (0,1):
            b=binding(parameters={"rise_time_us":edge,"fall_time_us":edge,"vin_width_us":3})
            for _,_,duration in slopes(b):self.assertAlmostEqual(duration,edge)
            plan=compile_scene({"channels":[b]},CATALOG)
            self.assertEqual(plan["channels"][0]["source"],"sram")
            if edge==0:self.assertEqual(set(plan["memory"]),{0,1024})
            else:self.assertGreater(len(set(plan["memory"])),2)

    def test_negative_pulses_use_voltage_direction(self):
        b=binding(20,parameters={"rise_time_us":.2,"fall_time_us":.4,"vin_width_us":1})
        for a,z,duration in slopes(b):self.assertAlmostEqual(duration,.2 if z>a else .4)

    def test_edges_are_not_clipped_to_half_width(self):
        b=binding(parameters={"rise_time_us":.8,"fall_time_us":.1,"vin_width_us":1})
        self.assertAlmostEqual(slopes(b)[0][2],.8)
        self.assertAlmostEqual(slopes(b)[1][2],.1)
        b["parameters"]["fall_time_us"]=.3
        with self.assertRaisesRegex(ValueError,"之和不能超过脉宽"):make_waveform(CATALOG,b)

    def test_invalid_edges_rejected_in_both_compilers(self):
        for key in ("rise_time_us","fall_time_us"):
            for value in (-.01,1.01,float("nan"),float("inf"),True,None):
                for static in (False,True):
                    with self.subTest(key=key,value=value,static=static):
                        scene=static_scene() if static else {"channels":[binding()]}
                        scene["channels"][0].setdefault("parameters",{})[key]=value
                        with self.assertRaisesRegex(ValueError,"0～1 μs"):compile_scene(scene,CATALOG)
                        self.assertFalse(public_preview(scene,CATALOG)["ok"])

    def test_ramps_and_stairs_apply_explicit_edges(self):
        for mode in (18,23):
            b=binding(mode,parameters={"rise_time_us":.4,"fall_time_us":.6,"vin_width_us":2})
            self.assertAlmostEqual(slopes(b)[0][2],.4)
            self.assertAlmostEqual(slopes(b)[1][2],.6)
        for mode,signal in ((5,"gate"),(7,"vin")):
            b=binding(mode,signal,topology=7,parameters={"stage1_voltage_v":3,"stage2_voltage_v":5,
                      "first_stage_us":1,"second_stage_us":2,"rise_time_us":.2,"fall_time_us":.4})
            changes=slopes(b)
            self.assertEqual(len(changes),3)
            for (_,_,duration),expected in zip(changes,(.2,.2,.4)):self.assertAlmostEqual(duration,expected)
            b["parameters"]["second_stage_us"]=.1
            with self.assertRaisesRegex(ValueError,"分段"):make_waveform(CATALOG,b)

    def test_all_catalog_variants_accept_full_range_edges(self):
        for entry in CATALOG["modes"]:
            if entry["mode"]>23:continue
            for case in entry["cases"]:
                for signal in ("vin","gate"):
                    for component in entry["components"]:
                        b=binding(entry["mode"],signal,topology=entry["topology"],variant=case["variant"],
                                  component=component,duration_us=100000,
                                  parameters={"rise_time_us":1,"fall_time_us":1})
                        with self.subTest(binding=b):make_waveform(CATALOG,b)

    def test_legacy_reference_edges_remain_compatible(self):
        b=binding(parameters={"rise_us":10,"fall_us":3})
        self.assertAlmostEqual(slopes(b)[0][2],1.25)
        self.assertAlmostEqual(slopes(b)[1][2],.375)
        self.assertTrue(public_preview({"channels":[b]},CATALOG)["ok"])

    def test_static_edges_use_single_sram_playback(self):
        scene=static_scene(10,10,10)
        scene["channels"][0]["parameters"].update(rise_time_us=.3,fall_time_us=.7)
        scene["channels"][1]["parameters"].update(rise_time_us=.5,fall_time_us=.4)
        plan=compile_scene(scene,CATALOG)
        self.assertNotEqual(plan["storage_mode"],"static_events")
        self.assertEqual(plan["hardware_pattern_repeats"],1)
        self.assertEqual((dict(plan["register_and_sram_writes"])[0x2a],dict(plan["register_and_sram_writes"])[0x2b]),(0,0))
        for row in plan["channels"][2:]:
            self.assertGreater(len(set(row["samples"])),2)
            self.assertEqual(row["samples"][-1],0)
        self.assertTrue(public_preview(scene,CATALOG)["ok"])

    def test_long_static_pulse_never_ignores_nonzero_edges(self):
        scene=static_scene()
        ideal=compile_scene(scene,CATALOG)
        for channel in scene["channels"]:channel["parameters"].update(rise_time_us=0,fall_time_us=0)
        self.assertEqual(compile_scene(scene,CATALOG)["packets"],ideal["packets"])
        scene["channels"][0]["parameters"]["rise_time_us"]=.5
        with self.assertRaisesRegex(ValueError,"非零上升/下降时间需要 SRAM"):
            compile_scene(scene,CATALOG)


if __name__=="__main__":unittest.main(verbosity=2)
