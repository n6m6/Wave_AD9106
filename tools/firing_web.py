"""Local-browser dashboard for four AD9106 Vin/Vgate channels (Python 3.8+)."""
import argparse
import json
import logging
import math
import threading
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from ad9106_firing import ROOT, compile_scene, export_plan, send_abort, send_plan, send_retrigger
from ad9106_diagnostics import read_registers
from firing_gui_core import available_ports, load_catalog, load_scene, probe_device, save_scene
from firing_waveforms import make_waveform, absolute_levels, binding_frequency, align_resonator_gate, binding_phase, binding_time_offset, rhythm_binding

ASSETS=Path(__file__).resolve().parent/"firing_web"
ASSET_TYPES={"/":"index.html","/app.js":"app.js","/style.css":"style.css"}
SCENE_PATH=ROOT/".uart_sim/firing_scene.json"
PLAN_PATH=ROOT/".uart_sim/firing_web_plan"
MAX_BODY=262144


def public_preview(scene,catalog):
    """Compile the complete scene; on error show each channel's template to aid repair."""
    try:
        plan=compile_scene(scene,catalog)
        step=plan["hold"]/plan["dac_clock_hz"]*1e6
        channels=[]
        for c in plan["channels"]:
            channels.append({
                "channel":c["channel"],"source":c["source"],
                "signal":c.get("signal"),"topology":c.get("topology"),
                "mode":c.get("mode"),"variant":c.get("variant"),"waveform":c.get("waveform"),
                "component":c.get("component"),"frequency_hz":c["frequency_hz"],
                "carrier_hz":c.get("sine_carrier_hz"),
                "period_us":1e6/c["frequency_hz"] if c["frequency_hz"] else None,
                "carrier_period_us":1e6/c["sine_carrier_hz"] if c.get("sine_carrier_hz") else None,
                "samples":c.get("samples",[c.get("constant_code",0)]),
                "sample_times_us":c.get("sample_times_us"),"pulse_width_us":c.get("pulse_width_us"),
                "total_samples":plan["samples_per_frame"] if c["source"]=="sram" else len(c.get("samples",[0])),
                "zero_tail_samples":c.get("zero_tail_samples",0),
                "zero_tail_us":c.get("zero_tail_samples",0)*step,
                "sram_words":c.get("sram_words",len(c.get("samples",[])) if c["source"]=="sram" else 0),
                "shared_with":c.get("shared_with",[]),
                "sampling_warnings":c.get("sampling_warnings",[]),
                "max_phase_quantization_deg":c.get("max_phase_quantization_deg"),
                "initial_phase_deg":c.get("initial_phase_deg"),
                "rise_time_us":c.get("rise_time_us"),"fall_time_us":c.get("fall_time_us"),
                "time_offset_us":c.get("time_offset_us",0),
                "step_us":c.get("preview_step_us",step),"duration_us":plan["pattern_duration_us"],
                "full_scale_v":plan["full_scale_v"],"zero_code_v":plan["zero_code_v"],
                "min_v":c.get("nominal_min_v",0),"max_v":c.get("nominal_max_v",0),
                "snapped":c.get("snapped_short_plateaus",0)})
        return {"ok":True,"channels":channels,
                "summary":{"frame_hz":plan["frame_frequency_hz"],"frame_duration_us":plan["pattern_duration_us"],
                           "max_duration_error_us":max((abs(1e6/c["frequency_hz"]-1e6/c["requested_frequency_hz"])
                               for c in plan["channels"] if c["frequency_hz"] and c.get("requested_frequency_hz")),default=0),
                           "sram_words":plan["sram_words"],
                           "hardware_pattern_repeats":plan["hardware_pattern_repeats"],
                           "static_pulse":plan.get("static_pulse",False),
                           "rhythm_modulation":plan.get("rhythm_modulation"),
                           "sram_free_words":4096-plan["sram_words"],
                           "sample_interval_us":step if any(c["source"]=="sram" for c in plan["channels"]) else None,
                           "hold":plan["hold"],"frequency_error_ppm":plan["frequency_error_ppm"],
                           "storage_mode":plan["storage_mode"],
                           "packet_count":len(plan["packets"])}}
    except (ValueError,KeyError,OverflowError,ZeroDivisionError) as error:
        rows={int(b["channel"]):b for b in scene.get("channels",[]) if isinstance(b,dict) and "channel" in b}
        waves={}; pairs={}
        for number,binding in rows.items():
            if not binding.get("enabled",True): continue
            try:
                waves[number]=make_waveform(catalog,binding)
                if binding.get("pair"): pairs.setdefault(binding["pair"],[]).append(binding)
            except (ValueError,KeyError,OverflowError,TypeError,ZeroDivisionError): pass
        for members in pairs.values():
            if len(members)!=2 or {b.get("signal") for b in members}!={"vin","gate"}: continue
            vin=next(b for b in members if b["signal"]=="vin"); gate=next(b for b in members if b["signal"]=="gate")
            if vin.get("mode")!=11 or gate.get("mode")!=11: continue
            if any(vin.get(k)!=gate.get(k) for k in ("topology","variant","component")): continue
            try:
                align_resonator_gate(waves[vin["channel"]][0],waves[gate["channel"]][0],binding_frequency(vin),
                    binding_frequency(gate),waves[gate["channel"]][2]["gate_range_v"][1])
            except (ValueError,KeyError,OverflowError,TypeError,ZeroDivisionError): pass
        channels=[]
        for number in range(1,5):
            binding=rows.get(number)
            if not binding or not binding.get("enabled",True):
                channels.append({"channel":number,"source":"disabled","samples":[0],
                                 "duration_us":10,"step_us":10,"full_scale_v":10,"zero_code_v":0})
                continue
            try:
                wave,_,case=waves[number] if number in waves else make_waveform(catalog,binding)
                frequency=float(binding_frequency(binding)) if wave.constant is None else 100000
                amplitude=float(binding.get("amplitude_v",10))
                offset=float(binding.get("offset_v",0))
                phase=binding_phase(binding,frequency) if wave.constant is None else 0
                if not all(math.isfinite(v) for v in (frequency,amplitude,offset,phase)) or frequency<=0:
                    raise ValueError("时长、幅值或偏移无效")
                peak=max(abs(v) for v in case[binding["signal"]+"_range_v"])
                scale=1 if absolute_levels(binding) else amplitude/peak if peak else 0
                samples=[wave.value(i/699+phase)*scale+offset for i in range(700)]
                rhythm=int(binding['mode']) in (27,28)
                carrier=float(binding_frequency(rhythm_binding(binding))) if rhythm else frequency
                channels.append({"channel":number,"source":"template","signal":binding["signal"],
                    "waveform":('sine' if int(binding['mode'])==27 and binding['signal']=='gate' else 'square') if rhythm else None,
                    "initial_phase_deg":binding.get('parameters',{}).get('rhythm_phase_deg',0) if rhythm else None,
                    "time_offset_us":binding_time_offset(binding,frequency) if wave.constant is None else 0,
                    "topology":binding["topology"],"mode":binding["mode"],
                    "frequency_hz":carrier,"period_us":1e6/carrier if wave.constant is None else None,
                    "carrier_period_us":wave.sine_period_us/wave.period_us*1e6/frequency if wave.sine_period_us else None,"samples":samples,
                    "duration_us":1e6/frequency,"step_us":1e6/frequency/699})
            except (ValueError,KeyError,OverflowError,TypeError,ZeroDivisionError) as suberror:
                channels.append({"channel":number,"source":"error","error":str(suberror),"samples":[]})
        return {"ok":False,"error":str(error),"channels":channels}


class DashboardServer(ThreadingHTTPServer):
    daemon_threads=True

    def __init__(self,address,handler= None):
        super().__init__(address,handler or DashboardHandler)
        self.catalog=load_catalog()
        self.scene_path=SCENE_PATH
        self.plan_path=PLAN_PATH
        self.lock=threading.Lock()
        self.connected_port=None
        self.job=None
        self.cancel_event=threading.Event()

    def initial_scene(self):
        path=self.scene_path if self.scene_path.exists() else ROOT/"waveforms/example_two_pairs.json"
        return load_scene(path)

    def start_send(self,scene,port):
        repeat_count=scene.get("repeat_count",1)
        interval_s=scene.get("interval_s",1)
        if isinstance(repeat_count,bool) or not isinstance(repeat_count,int) or not 1<=repeat_count<=1000:
            raise ValueError("本次播放次数必须是 1～1000 的整数")
        if isinstance(interval_s,bool) or not isinstance(interval_s,(int,float)) or not math.isfinite(interval_s) or not .01<=interval_s<=3600:
            raise ValueError("完整波形之间的间隔必须是 0.01～3600 秒")
        with self.lock:
            if self.job and self.job["status"]=="running":
                raise ValueError("已有上传任务正在运行")
            if port!=self.connected_port:
                raise ValueError("请先检测当前串口与 AD9106 指令解析器的连接")
            plan=compile_scene(scene,self.catalog)
            export_plan(plan,self.plan_path)
            save_scene(self.scene_path,scene)
            job={"id":uuid.uuid4().hex,"status":"running","done":0,
                 "total":len(plan["packets"])+repeat_count-1,"cycle":0,
                 "repeat_count":repeat_count,"message":"正在发送"}
            self.job=job
            self.cancel_event.clear()

        def run():
            def progress(done,total):
                if self.cancel_event.is_set(): raise ValueError("用户停止播放")
                with self.lock: job["done"]=done
            try:
                for cycle in range(repeat_count):
                    if self.cancel_event.is_set(): break
                    with self.lock:
                        job["cycle"]=cycle
                        job["message"]="正在发送第 {}/{} 组触发（每组 {} 遍）".format(cycle+1,repeat_count,plan["hardware_pattern_repeats"])
                    if cycle==0: send_plan(plan,port,progress=progress)
                    else:
                        send_retrigger(port)
                        with self.lock: job["done"]+=1
                    if cycle+1<repeat_count:
                        with self.lock: job["message"]="第 {} 组已触发，等待播放完成及 {} 秒间隔".format(cycle+1,interval_s)
                        if self.cancel_event.wait(interval_s+plan["burst_duration_us"]/1e6):
                            break
                    elif plan.get("static_pulse") or plan.get("finite_window"):
                        with self.lock: job["message"]="单次波形已触发，等待观察窗结束并归零"
                        self.cancel_event.wait(plan["burst_duration_us"]/1e6)
                if self.cancel_event.is_set():
                    send_abort(port)
                    with self.lock: job["status"]="cancelled";job["message"]="已停止后续播放"
                    return
                with self.lock:
                    job["status"]="complete"; job["message"]="已发送 {} 次触发，每次触发连续播放 {} 个预览单元".format(repeat_count,plan["hardware_pattern_repeats"])
            except Exception as error:
                with self.lock:
                    if self.cancel_event.is_set():
                        job["status"]="cancelled"; job["message"]="已停止后续播放"
                    else:
                        job["status"]="error"; job["message"]=str(error)
                        self.connected_port=None
        threading.Thread(target=run,name="ad9106-upload",daemon=True).start()
        return dict(job)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version="AD9106Dashboard/1.0"

    def log_message(self,format,*args):
        logging.info("%s %s",self.address_string(),format%args)

    def _allowed_host(self):
        value=self.headers.get("Host","").lower()
        return value in ("127.0.0.1:{}".format(self.server.server_port),
                         "localhost:{}".format(self.server.server_port))

    def _json(self,payload,status=200):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def _error(self,message,status=400): self._json({"error":str(message)},status)

    def _body(self):
        if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
            raise ValueError("Content-Type 必须为 application/json")
        origin=self.headers.get("Origin")
        if origin and origin.lower() not in (
            "http://127.0.0.1:{}".format(self.server.server_port),
            "http://localhost:{}".format(self.server.server_port)):
            raise ValueError("请求来源不是当前控制台")
        try: size=int(self.headers.get("Content-Length","0"))
        except ValueError: raise ValueError("Content-Length 无效")
        if size<1 or size>MAX_BODY: raise ValueError("请求内容为空或过大")
        data=json.loads(self.rfile.read(size).decode("utf-8"))
        if not isinstance(data,dict): raise ValueError("请求内容应为 JSON 对象")
        return data

    def _port(self,body):
        port=body.get("port")
        if not isinstance(port,str) or port not in {p[0] for p in available_ports()}:
            raise ValueError("选择的串口当前不可用，请刷新列表")
        return port

    def do_GET(self):
        if not self._allowed_host(): return self._error("仅允许本机访问",403)
        route=urlsplit(self.path).path
        if route in ASSET_TYPES:
            filename=ASSET_TYPES[route]
            data=(ASSETS/filename).read_bytes()
            mime="text/html" if filename.endswith("html") else "text/javascript" if filename.endswith("js") else "text/css"
            self.send_response(200); self.send_header("Content-Type",mime+"; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(data)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'")
            self.end_headers(); self.wfile.write(data)
            return
        if route=="/api/bootstrap":
            return self._json({"catalog":self.server.catalog,"scene":self.server.initial_scene()})
        if route=="/api/ports":
            try:
                import serial
                serial_ready=hasattr(serial,"Serial")
            except ImportError: serial_ready=False
            return self._json({"ports":[{"device":p,"description":d} for p,d in available_ports()],
                               "pyserial_available":serial_ready})
        if route=="/api/job":
            job_id=parse_qs(urlsplit(self.path).query).get("id",[""])[0]
            with self.server.lock:
                job=dict(self.server.job) if self.server.job and self.server.job["id"]==job_id else None
            return self._json(job or {"error":"任务不存在"},200 if job else 404)
        return self._error("页面不存在",404)

    def do_POST(self):
        if not self._allowed_host(): return self._error("仅允许本机访问",403)
        try:
            body=self._body(); route=urlsplit(self.path).path
            if route=="/api/preview":
                if not isinstance(body.get("scene"),dict): raise ValueError("场景必须是 JSON 对象")
                return self._json(public_preview(body["scene"],self.server.catalog))
            if route=="/api/save":
                scene=body["scene"]
                if not isinstance(scene,dict) or not isinstance(scene.get("channels"),list):
                    raise ValueError("场景缺少 channels 列表")
                save_scene(self.server.scene_path,scene)
                return self._json({"message":"配置已保存到 "+str(self.server.scene_path)})
            if route=="/api/probe":
                port=self._port(body)
                with self.server.lock:
                    if self.server.job and self.server.job["status"]=="running":
                        raise ValueError("上传期间不能切换串口")
                    self.server.connected_port=None
                message=probe_device(port)
                with self.server.lock: self.server.connected_port=port
                return self._json({"message":message,"port":port})
            if route=="/api/send":
                port=self._port(body)
                return self._json(self.server.start_send(body["scene"],port))
            if route=="/api/registers":
                port=self._port(body)
                with self.server.lock:
                    if self.server.job and self.server.job["status"]=="running":
                        raise ValueError("请等待本次播放任务完成后回读")
                    if port!=self.server.connected_port:
                        raise ValueError("请先检测当前串口")
                    result=read_registers(port)
                return self._json(result)
            if route=="/api/abort":
                port=self._port(body)
                with self.server.lock:
                    if self.server.job and self.server.job["status"]=="running":
                        self.server.cancel_event.set()
                        return self._json({"message":"已请求停止；当前发送帧完成后终止后续播放"})
                    if port!=self.server.connected_port:
                        raise ValueError("请先检测当前串口")
                send_abort(port)
                return self._json({"message":"四路输出已停止，数字增益和偏移已清零"})
            return self._error("接口不存在",404)
        except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError) as error:
            return self._error(error)
        except OSError as error: return self._error(error,503)
        except Exception:
            logging.exception("Dashboard request failed")
            return self._error("服务处理失败；请查看启动终端日志",500)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=0,help="本机服务端口；默认使用空闲端口")
    parser.add_argument("--no-browser",action="store_true",help="仅打印地址，不自动打开浏览器")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    server=DashboardServer(("127.0.0.1",args.port))
    url="http://127.0.0.1:{}/".format(server.server_port)
    print("AD9106 控制台："+url,flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=="__main__": main()
