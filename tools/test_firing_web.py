"""Local dashboard API, serial probe and four-channel upload regression."""
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from firing_gui_core import load_catalog, load_scene, probe_device
from firing_web import DashboardServer, public_preview


ROOT=Path(__file__).resolve().parents[1]
CATALOG=load_catalog()


class FakeSerial:
    sent=[]

    def __init__(self,port,baud,**kwargs):
        self.port=port; self.baud=baud; self.last=None
        self.__class__.sent.append(self)

    def __enter__(self): return self
    def __exit__(self,*args): return False
    def reset_input_buffer(self): pass
    def write(self,packet): self.last=bytes(packet); return len(packet)
    def flush(self): pass
    def read(self,count):
        seq,command=self.last[2:4]
        status=3 if command==0x7f else 0
        return bytes([0x55,0xaa,seq,command,status,seq^command^status,13,10])


class WebTests(unittest.TestCase):
    def setUp(self):
        FakeSerial.sent=[]
        self.scene=load_scene(ROOT/"waveforms/example_two_pairs.json")

    def test_1khz_preview_keeps_full_time_axis(self):
        scene={"channels":[dict(channel=3,topology=6,mode=24,signal="vin",
                                frequency_hz=1000,amplitude_v=5,
                                parameters={"period_us":1000,"start_us":10,"width_us":10})]}
        preview=public_preview(scene,CATALOG)
        self.assertTrue(preview["ok"])
        row=preview["channels"][2]
        self.assertEqual(row["duration_us"],1000)
        self.assertEqual(row["total_samples"],len(row["samples"])+row["zero_tail_samples"])
        self.assertGreater(row["zero_tail_us"],979)
        self.assertEqual(preview["summary"]["storage_mode"],"zero_tail")

    def test_four_channel_public_preview_and_resource_error(self):
        preview=public_preview(self.scene,CATALOG)
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"]["sram_words"],3960)
        self.assertEqual(preview["summary"]["packet_count"],590)
        self.assertEqual([c["frequency_hz"] for c in preview["channels"]],
                         [50000,50000,100000,100000])
        self.scene["channels"][1]["frequency_hz"]=60000
        self.assertTrue(public_preview(self.scene,CATALOG)["ok"])
        self.scene["channels"][1]["frequency_hz"]=60001
        bad=public_preview(self.scene,CATALOG)
        self.assertFalse(bad["ok"])
        self.assertEqual(len(bad["channels"]),4)

    def test_probe_is_a_read_only_unknown_command(self):
        result=probe_device("COM9",serial_factory=FakeSerial)
        self.assertIn("COM9",result)
        self.assertEqual(FakeSerial.sent[0].last[3],0x7f)
        self.assertEqual(len(FakeSerial.sent[0].last),24)

    def test_http_dashboard_probe_upload_stop(self):
        opener=build_opener(ProxyHandler({}))
        with tempfile.TemporaryDirectory() as directory:
            server=DashboardServer(("127.0.0.1",0))
            server.scene_path=Path(directory)/"scene.json"
            server.plan_path=Path(directory)/"plan"
            worker=threading.Thread(target=server.serve_forever,daemon=True)
            worker.start()
            base="http://127.0.0.1:{}".format(server.server_port)
            def get(route):
                with opener.open(base+route,timeout=10) as response:
                    return response.status,response.read()
            def post(route,body,headers=None):
                request=Request(base+route,json.dumps(body).encode("utf-8"),
                    {"Content-Type":"application/json",**(headers or {})},method="POST")
                with opener.open(request,timeout=10) as response:
                    return json.loads(response.read())
            fake_module=types.SimpleNamespace(Serial=FakeSerial)
            try:
                with patch.dict(sys.modules,{"serial":fake_module}),\
                     patch("firing_web.available_ports",return_value=[("COM9","Mock port")]):
                    status,html=get("/"); self.assertEqual(status,200)
                    self.assertIn(b"channelEditors",html)
                    self.assertIn(b"schedulePreview",get("/app.js")[1])
                    boot=json.loads(get("/api/bootstrap")[1]); self.assertEqual(len(boot["catalog"]["modes"]),104)
                    self.assertEqual(len(boot["scene"]["channels"]),4)
                    self.assertEqual(json.loads(get("/api/ports")[1])["ports"][0]["device"],"COM9")
                    with self.assertRaises(HTTPError) as invalid:
                        post("/api/send",{"port":"COM9","scene":self.scene})
                    self.assertEqual(invalid.exception.code,400)
                    self.assertEqual(post("/api/probe",{"port":"COM9"})["port"],"COM9")
                    self.assertEqual(FakeSerial.sent[0].last[3],0x7f)
                    unsupported={"channels":[dict(channel=3,topology=6,mode=24,signal="vin",
                        frequency_hz=1000,amplitude_v=5,
                        parameters={"period_us":1000,"start_us":10,"width_us":600})]}
                    with self.assertRaises(HTTPError) as rejected:
                        post("/api/send",{"port":"COM9","scene":unsupported})
                    self.assertEqual(rejected.exception.code,400)
                    self.assertEqual(len(FakeSerial.sent),1) # Probe only, no upload/trigger.
                    with patch("firing_web.read_registers",return_value={"registers":{"0x1F":1},"finite_once":True}) as readback:
                        self.assertTrue(post("/api/registers",{"port":"COM9"})["finite_once"])
                        readback.assert_called_once_with("COM9")
                        with self.assertRaises(HTTPError):
                            post("/api/registers",{"port":"COM8"})
                        readback.assert_called_once()
                    summary=post("/api/preview",{"scene":self.scene})
                    self.assertTrue(summary["ok"])
                    with self.assertRaises(HTTPError) as cross_origin:
                        post("/api/probe",{"port":"COM9"},{"Origin":"http://evil.invalid"})
                    self.assertEqual(cross_origin.exception.code,400)
                    scene={**self.scene,"repeat_count":2,"interval_s":.01}
                    scene=json.loads(json.dumps(scene))
                    for channel in scene["channels"]:
                        channel["duration_us"]=1e6/channel.pop("frequency_hz")
                    job=post("/api/send",{"port":"COM9","scene":scene})
                    deadline=time.monotonic()+6
                    while time.monotonic()<deadline:
                        result=json.loads(get("/api/job?id="+job["id"])[1])
                        if result["status"]!="running": break
                        time.sleep(.02)
                    self.assertEqual(result["status"],"complete")
                    self.assertEqual(result["done"],591)
                    self.assertEqual(FakeSerial.sent[1].last[3],0x42)
                    self.assertEqual(FakeSerial.sent[2].last[3],0x44)
                    self.assertTrue(server.plan_path.joinpath("plan.json").exists())
                    saved=json.loads(server.scene_path.read_text(encoding="utf-8"))
                    self.assertEqual(saved["channels"][0]["duration_us"],20)
                    self.assertNotIn("frequency_hz",saved["channels"][0])
                    self.assertEqual(post("/api/abort",{"port":"COM9"})["message"][:2],"四路")
                    self.assertEqual(FakeSerial.sent[-1].last[3],0x43)
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=3)


if __name__=="__main__": unittest.main(verbosity=2)
