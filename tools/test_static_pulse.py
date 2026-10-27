"""Finite static pulses: event voltages/timing, SRAM fallback and exported preview."""
import csv
import tempfile
import unittest
from pathlib import Path

from ad9106_firing import compile_scene, export_plan
from firing_gui_core import load_catalog
from firing_web import public_preview

CATALOG=load_catalog()


def scene(width=2000,lead=300,tail=300):
    return dict(static_pulse=True,repeat_count=1,channels=[
        dict(channel=3,topology=6,mode=24,signal='vin',pair='B',amplitude_v=1,parameters={'width_us':width}),
        dict(channel=4,topology=6,mode=24,signal='gate',pair='B',amplitude_v=2,
             parameters={'gate_lead_us':lead,'gate_tail_us':tail})])


class StaticPulseTests(unittest.TestCase):
    def test_2ms_gate_envelope_and_final_zero(self):
        p=compile_scene(scene(),CATALOG)
        self.assertEqual(p['storage_mode'],'static_events')
        self.assertEqual(p['sram_words'],0)
        self.assertEqual(p['hardware_pattern_repeats'],1)
        events=p['basic_events']
        self.assertEqual([e['ticks'] for e in events],[30000,60000,260000,290000])
        # Word order: deadline, DAC4..1 constant codes, DAC4..1 gains.
        self.assertEqual([e['words'][6:] for e in events],
                         [[0x4000,0,0,0],[0x4000,0x4000,0,0],[0x4000,0,0,0],[0,0,0,0]])
        self.assertEqual(events[-1]['words'][2:],[0]*8)
        self.assertEqual(events[0]['words'][2],410<<4)
        self.assertEqual(events[1]['words'][3],205<<4)
        self.assertFalse(any(0x6000<=a<0x7000 for a,_ in p['register_and_sram_writes']))
        self.assertEqual([bytes.fromhex(packet)[3] for packet in p['packets']].count(0x42),1)

    def test_longer_pulses_do_not_consume_more_sram(self):
        p=compile_scene(scene(2000000,500,800),CATALOG)
        self.assertEqual(p['sram_words'],0)
        self.assertAlmostEqual(p['channels'][2]['pulse_width_us'],2000000)
        self.assertAlmostEqual(p['channels'][3]['pulse_width_us'],2001300)

    def test_short_complete_shape_falls_back_to_single_sram_pattern(self):
        p=compile_scene(scene(10,10,10),CATALOG)
        self.assertGreater(p['sram_words'],0)
        self.assertEqual(p['hardware_pattern_repeats'],1)
        regs=dict(p['register_and_sram_writes'])
        self.assertEqual((regs[0x2a],regs[0x2b]),(0,0))
        for row in p['channels'][2:]:
            self.assertEqual(row['samples'][-1],0)

    def test_long_pulse_does_not_silently_stretch_short_margins(self):
        with self.assertRaisesRegex(ValueError,'300'):
            compile_scene(scene(2000,10,10),CATALOG)

    def test_zero_margins_use_simultaneous_edges(self):
        p=compile_scene(scene(2000,0,0),CATALOG)
        self.assertEqual(len(p['basic_events']),2)
        self.assertEqual(p['channels'][2]['pulse_width_us'],2000)

    def test_rejects_invalid_or_unbounded_requests(self):
        for width in (0,-1,float('nan'),float('inf'),True,43000000):
            with self.subTest(width=width),self.assertRaises(ValueError):
                compile_scene(scene(width),CATALOG)
        s=scene();s['repeat_count']=2
        with self.assertRaisesRegex(ValueError,'一次'): compile_scene(s,CATALOG)
        s=scene();s['channels'][1]['pair']='unknown'
        with self.assertRaisesRegex(ValueError,'配对'): compile_scene(s,CATALOG)

    def test_preview_and_csv_use_real_event_times(self):
        s=scene();p=compile_scene(s,CATALOG);preview=public_preview(s,CATALOG)
        self.assertTrue(preview['ok'])
        row=preview['channels'][2]
        self.assertEqual(row['sample_times_us'],[0,300,300,2300,2300,2600])
        self.assertEqual(row['duration_us'],2600)
        with tempfile.TemporaryDirectory() as directory:
            export_plan(p,directory)
            with (Path(directory)/'dac3.csv').open() as f: rows=list(csv.DictReader(f))
            self.assertEqual([float(r['time_us']) for r in rows],row['sample_times_us'])
            self.assertEqual(int(rows[-1]['code']),0)


if __name__=='__main__': unittest.main()
