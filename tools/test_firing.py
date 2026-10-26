"""Semantic, protocol and capacity tests for the graph-derived waveform library."""
import json
import math
import unittest
from pathlib import Path

from ad9106_firing import compile_scene, frame, voltage_code, sample_wave
from firing_waveforms import make_waveform, Waveform
from firing_gui_core import load_catalog

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/"waveforms/firing_catalog.json").read_text(encoding="utf-8"))


def binding(mode,signal="vin",topology=6,**values):
    data=dict(channel=1,topology=topology,mode=mode,signal=signal,frequency_hz=100000)
    data.update(values); return data


class FiringTests(unittest.TestCase):
    def test_1khz_static_keeps_every_sample_and_two_repeats(self):
        channels=[binding(24,signal,channel=ch,frequency_hz=1000,amplitude_v=amp,
                          parameters={"period_us":1000,"start_us":10,"width_us":10})
                  for ch,signal,amp in ((3,"vin",5),(4,"gate",8))]
        scene={"channels":channels}
        original=json.dumps(scene,sort_keys=True)
        plan=compile_scene(scene,load_catalog())
        vin=plan["channels"][2]
        self.assertEqual(json.dumps(scene,sort_keys=True),original)
        self.assertEqual(plan["storage_mode"],"zero_tail")
        self.assertEqual(plan["frame_frequency_hz"],1000)
        self.assertEqual(plan["hardware_pattern_repeats"],2)
        self.assertEqual(plan["burst_duration_us"],2000)
        self.assertLessEqual(plan["sram_words"],4096)
        self.assertEqual(vin["snapped_short_plateaus"],0)
        wave,_,_=make_waveform(load_catalog(),channels[0])
        full,_=sample_wave(wave,plan["samples_per_frame"],1,0,5,0,10,0,strict=True)
        self.assertEqual(vin["samples"]+[0]*vin["zero_tail_samples"],full)
        self.assertEqual(sum(a==0 and b>0 for a,b in zip(full,full[1:])),1)
        regs=dict(plan["register_and_sram_writes"])
        self.assertEqual(regs[0x29]*(regs[0x28]>>4&15 or 16),148500)
        self.assertEqual((regs[0x56]>>4)-(regs[0x55]>>4)+1,len(vin["samples"]))
        self.assertEqual(regs[0x2a],0x0101)

    def test_1khz_extension_rejects_nonzero_tail_and_long_wave(self):
        for channel in (
            binding(24,frequency_hz=1000,offset_v=1,
                    parameters={"period_us":1000,"start_us":10,"width_us":10}),
            binding(24,frequency_hz=1000,
                    parameters={"period_us":1000,"start_us":10,"width_us":600}),
            binding(10,"gate",frequency_hz=1000),
        ):
            scene={"channels":[channel]}; original=json.dumps(scene,sort_keys=True)
            with self.assertRaisesRegex(ValueError,"保留波形细节"):
                compile_scene(scene,load_catalog())
            self.assertEqual(json.dumps(scene,sort_keys=True),original)

    def test_strict_sampling_never_stretches_short_details(self):
        wave=Waveform(1000,points=[(0,0),(10,0),(10.01,1),(10.02,1),(10.03,0),(1000,0)])
        with self.assertRaisesRegex(ValueError,"不足一个"):
            sample_wave(wave,10000,1,0,1,0,10,0,sample_count=102,strict=True)

    def test_static_scan_single_pulse_unit_and_two_hardware_repeats(self):
        params={"period_us":100,"start_us":10,"width_us":8}
        channels=[dict(channel=n,topology=6,mode=24,signal=signal,
                       frequency_hz=10000,amplitude_v=amplitude,parameters=params)
                  for n,signal,amplitude in ((3,"vin",2),(4,"gate",3))]
        catalog=load_catalog()
        vin,_,_=make_waveform(catalog,channels[0])
        gate,_,_=make_waveform(catalog,channels[1])
        self.assertEqual([vin.value(t/100) for t in (5,11,17,20,80)],[0,1,1,0,0])
        self.assertEqual([gate.value(t/100) for t in (5,50,95)],[1,1,1])
        plan=compile_scene({"channels":channels},catalog)
        self.assertIn((0x1f,1),plan["register_and_sram_writes"])
        self.assertIn((0x2a,0x0101),plan["register_and_sram_writes"])
        self.assertIn((0x2b,0x0101),plan["register_and_sram_writes"])
        self.assertAlmostEqual(plan["pattern_duration_us"],100)
        self.assertEqual(plan["hardware_pattern_repeats"],2)
        self.assertAlmostEqual(plan["burst_duration_us"],200)
        self.assertFalse(any(address==0x7ffe for address,_ in plan["register_and_sram_writes"]))
        self.assertFalse(any(address==0x7ffe for address,_ in plan["spi_oracle"]))
        self.assertEqual(plan["channels"][2]["signal"],"vin")
        self.assertEqual(plan["channels"][2]["source"],"sram")
        self.assertEqual(plan["channels"][3]["signal"],"gate")
        self.assertEqual(plan["channels"][3]["source"],"constant")
        too_wide=[{**c,"parameters":{**params,"width_us":85}} for c in channels]
        wide=compile_scene({"channels":too_wide},catalog)
        samples=wide["channels"][2]["samples"]
        self.assertEqual(sum(a==0 and b>0 for a,b in zip(samples,samples[1:])),1)
        self.assertEqual(wide["channels"][2]["cycles_per_frame"],1)

    def test_catalog_is_complete(self):
        self.assertEqual(len(CATALOG["modes"]),92)
        self.assertEqual(sum(len(e["cases"]) for e in CATALOG["modes"]),163)

    def test_all_variants_and_components_compile(self):
        count=0
        for entry in CATALOG["modes"]:
            for case in entry["cases"]:
                for signal in ("vin","gate"):
                    for component in entry["components"]:
                        b=binding(entry["mode"],signal,entry["topology"],variant=case["variant"],component=component)
                        with self.subTest(topology=entry["topology"],mode=entry["mode"],variant=case["variant"],signal=signal,component=component):
                            plan=compile_scene({"channels":[b]},CATALOG)
                            self.assertLessEqual(plan["sram_words"],4096)
                            self.assertEqual(len(plan["channels"]),4)
                            self.assertLess(plan["frequency_error_ppm"],1000.001)
                            self.assertTrue(all(-2048<=v<=2047 for v in plan["memory"]))
                            count+=1
        self.assertEqual(count,504)

    def test_burst_and_onset_gate(self):
        vin,_,_=make_waveform(CATALOG,binding(3))
        gate,_,_=make_waveform(CATALOG,binding(3,"gate"))
        self.assertEqual(vin.value(30/220),5)
        self.assertEqual(gate.value(30/220),6.8)
        self.assertEqual(gate.value(50/220),0)
        self.assertEqual(gate.value(70/220),6.8)
        onset,_,_=make_waveform(CATALOG,binding(4,"gate"))
        self.assertEqual(onset.value(70/220),0)

    def test_multi_level_sequence_and_selection(self):
        seq,_,_=make_waveform(CATALOG,binding(21))
        for t,v in [(21,3),(76,4.7),(131,5)]: self.assertAlmostEqual(seq.value(t/180),v)
        low,_,_=make_waveform(CATALOG,binding(21,component="low"))
        self.assertEqual(low.value(21/180),3)
        self.assertEqual(low.value(76/180),0)
        slow,_,_=make_waveform(CATALOG,binding(18,variant=1))
        fast,_,_=make_waveform(CATALOG,binding(18,variant=0))
        self.assertEqual(fast.value(60/200),5)
        self.assertAlmostEqual(slow.value(60/200),2.5)

    def test_negative_release_and_integrator_constant_gate(self):
        wave,_,_=make_waveform(CATALOG,binding(13))
        self.assertEqual(wave.value(40/160),-5)
        self.assertEqual(wave.value(120/160),0)
        gate,_,_=make_waveform(CATALOG,binding(12,"gate"))
        self.assertEqual(gate.value(19/210),7.1)
        self.assertEqual(gate.value(20.1/210),7.1)
        self.assertEqual(gate.value(20.8/210),7.1)

    def test_sine_carrier_is_continuous(self):
        wave,_,_=make_waveform(CATALOG,binding(11,"gate",topology=5))
        self.assertEqual(wave.continuity_multiple,2)
        self.assertAlmostEqual(wave.value(1),2.49993)
        self.assertAlmostEqual(wave.value(2),0)
        plan=compile_scene({"channels":[binding(11,"gate",topology=5)]},CATALOG)
        channel=plan["channels"][0]
        self.assertEqual(channel["cycles_per_frame"]%2,0)
        self.assertAlmostEqual(channel["sine_carrier_hz"],1250000)

    def test_four_channels_and_pair_synchronization(self):
        cfg=json.loads((ROOT/"waveforms/example_two_pairs.json").read_text())
        plan=compile_scene(cfg,CATALOG)
        self.assertEqual(plan["storage_mode"],"full_frame")
        self.assertEqual([c["frequency_hz"] for c in plan["channels"]],[50000,50000,100000,100000])
        self.assertEqual([c["cycles_per_frame"] for c in plan["channels"]],[1,1,2,2])
        self.assertEqual(plan["sram_words"],3960)
        self.assertEqual(plan["hold"],3)
        cfg["channels"][1]["phase_deg"]=90
        with self.assertRaisesRegex(ValueError,"配对.*相位"): compile_scene(cfg,CATALOG)

    def test_channel_assignment_is_not_fixed(self):
        for channel in (1,2,3,4):
            plan=compile_scene({"channels":[binding(19,channel=channel,amplitude_v=5)]},CATALOG)
            active=plan["channels"][channel-1]
            self.assertEqual(active["min_code"],-1024)
            self.assertEqual(sum(c["source"]=="sram" for c in plan["channels"]),1)

    def test_capacity_and_voltage_errors(self):
        with self.assertRaisesRegex(ValueError,"cannot fit"):
            compile_scene({"channels":[binding(10,"gate",frequency_hz=5000),binding(10,"gate",channel=2,frequency_hz=6000)]},CATALOG)
        with self.assertRaises(ValueError): voltage_code(12,10,0)
        with self.assertRaises(ValueError): compile_scene({"channels":[binding(1,amplitude_v=11)]},CATALOG)
        self.assertEqual(voltage_code(-10,10,0),-2048)
        self.assertEqual(voltage_code(10,10,0),2047)

    def test_distinct_narrow_events_cannot_merge(self):
        wave=Waveform(100,points=[(0,0),(1,0),(1,5),(1.1,5),(1.1,0),
                                 (1.2,0),(1.2,5),(1.3,5),(1.3,0),(100,0)])
        with self.assertRaisesRegex(ValueError,"collide"):
            sample_wave(wave,32,1,0,1,0,10,0)

    def test_packets_and_register_mapping(self):
        plan=compile_scene({"channels":[binding(1,channel=4)]},CATALOG)
        packets=[bytes.fromhex(p) for p in plan["packets"]]
        self.assertEqual(packets[0][3],0x40); self.assertEqual(packets[-1][3],0x42)
        decoded=[]
        for packet in packets:
            self.assertEqual(len(packet),24)
            checksum=0
            for value in packet[2:22]: checksum^=value
            self.assertEqual(checksum,packet[22])
            if packet[3]==0x41:
                addr=int.from_bytes(packet[4:6],"big"); count=packet[6]
                self.assertTrue(1<=count<=7)
                for i in range(count): decoded.append((addr+i,int.from_bytes(packet[7+2*i:9+2*i],"big")))
        self.assertEqual(decoded,plan["register_and_sram_writes"])
        regs={a:v for a,v in decoded if a<0x6000}
        self.assertEqual(regs[0x26],0x0001) # DAC4 SRAM, DAC3 constant.
        self.assertEqual(regs[0x27],0x0101) # DAC2 and DAC1 constant.
        self.assertEqual(plan["spi_oracle"][-2:],[(0x1e,1),(0x1d,1)])


if __name__=="__main__": unittest.main(verbosity=2)
