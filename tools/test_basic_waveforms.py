import copy
import json
import unittest
from pathlib import Path
from ad9106_firing import compile_scene
from firing_gui_core import load_catalog
from firing_web import public_preview

ROOT=Path(__file__).resolve().parents[1]

class BasicTests(unittest.TestCase):
    def setUp(self):
        self.scene=json.loads((ROOT/'waveforms/example_basic_1khz.json').read_text())
        self.catalog=load_catalog()

    def test_both_modes_1khz_and_finite_zero_end(self):
        plan=compile_scene(self.scene,self.catalog)
        regs=dict(plan['register_and_sram_writes'])
        self.assertEqual(regs[0x7101],5)
        self.assertEqual([e['ticks'] for e in plan['basic_events']],[30000,80000,130000,180000,230000])
        self.assertEqual(plan['basic_events'][-1]['words'][2:],[0]*8)
        # DAC1 square codes: 4 V, 0 V, 4 V, 0 V, then final mute.
        self.assertEqual([e['words'][5] for e in plan['basic_events']],[819<<4,0,819<<4,0,0])
        self.assertEqual(regs[0x26],0x3201)
        self.assertEqual(regs[0x27],0x3201)
        self.assertEqual(regs[0x40],0x4000)
        self.assertEqual(regs[0x53],1)
        self.assertEqual(plan['hardware_pattern_repeats'],2)
        self.assertAlmostEqual(plan['channels'][1]['frequency_hz'],113*148500000/2**24)
        self.assertEqual(plan['sram_words'],0)
        self.assertFalse(any(a>=0x7100 for a,_ in plan['spi_oracle']))

    def test_unrepresentable_edges_and_shared_dds_rejected(self):
        for kind in ('duty','dds','voltage','phase'):
            scene=copy.deepcopy(self.scene)
            if kind=='duty': scene['channels'][0]['parameters']['duty_percent']=10
            if kind=='dds': scene['channels'][3]['frequency_hz']=2000
            if kind=='voltage': scene['channels'][0]['amplitude_v']=9
            if kind=='phase': scene['channels'][0]['phase_deg']=90
            before=copy.deepcopy(scene)
            with self.assertRaises(ValueError): compile_scene(scene,self.catalog)
            self.assertEqual(scene,before)

    def test_preview_duration_and_shape(self):
        p=public_preview(self.scene,self.catalog)
        self.assertTrue(p['ok'])
        self.assertEqual([r['source'] for r in p['channels']],['fpga_square','dds','fpga_square','dds'])
        for r in p['channels']:
            self.assertAlmostEqual(r['duration_us'],1000)
            self.assertEqual(r['total_samples'],1000)
        self.assertGreater(p['channels'][1]['samples'][250],p['channels'][1]['samples'][0])

    def test_square_duty_and_independent_frequencies(self):
        scene=copy.deepcopy(self.scene)
        scene['channels']=[scene['channels'][0]]
        scene['channels'][0]['parameters']['duty_percent']=30
        plan=compile_scene(scene,self.catalog)
        self.assertEqual([e['ticks'] for e in plan['basic_events']],
                         [30000,60000,130000,160000,230000])
        scene=copy.deepcopy(self.scene)
        scene['channels']=[scene['channels'][0],scene['channels'][2]]
        scene['channels'][0]['frequency_hz']=500
        plan=compile_scene(scene,self.catalog)
        self.assertEqual([r['frequency_hz'] for r in plan['channels'] if r['source']=='fpga_square'],[500,1000])
        self.assertEqual(plan['pattern_duration_us'],2000)
        self.assertEqual(len(plan['basic_events']),9)

    def test_sine_only_and_legacy_dynamic_rejection(self):
        scene=copy.deepcopy(self.scene)
        scene['channels']=[scene['channels'][1]]
        plan=compile_scene(scene,self.catalog)
        self.assertEqual(len(plan['basic_events']),2)
        self.assertEqual(dict(plan['register_and_sram_writes'])[0x5b],1)
        # Full DDS cycle plus start latency fits before the final mute event.
        self.assertGreaterEqual(plan['pattern_duration_us'],
            1e6/plan['channels'][1]['frequency_hz']+24/148.5)
        scene['channels'].append(dict(channel=3,mode=24,topology=6,signal='vin',
            frequency_hz=1000,amplitude_v=1,parameters=dict(period_us=1000,width_us=10)))
        with self.assertRaisesRegex(ValueError,'关闭其他动态模板'):
            compile_scene(scene,self.catalog)

if __name__=='__main__': unittest.main()
