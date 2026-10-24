"""Nonvisual serial/scene helpers for the AD9106 desktop controller."""
import json
import sys
from pathlib import Path

from ad9106_firing import ROOT, STATUS, frame, decode_reply


def load_catalog():
    catalog=json.loads((ROOT/"waveforms/firing_catalog.json").read_text(encoding="utf-8"))
    for topology in (3,5,6,7):
        catalog["modes"].append({"topology":topology,"mode":24,"name":"Static scan",
            "description":"Vgate 恒压，Vin 单个可调宽度方波；当前每次触发连续执行两遍单元。",
            "components":["pulse"],"cases":[{"variant":0,"experiment":"static_scan",
            "vin_range_v":[0,1],"gate_range_v":[0,1]}]})
        for mode,name,description in ((25,"square","FPGA 定时方波：幅值为中心到峰值，偏移为中心电压，占空比可调；过短切换间隔会拒绝。"),
                                      (26,"sine","芯片 DDS 正弦波：幅值、偏移、相位可调；多路正弦共用频率，显示量化后实际频率。")):
            catalog["modes"].append({"topology":topology,"mode":mode,"name":name,
                "description":description,"components":[name],"cases":[{"variant":0,"experiment":name,
                "vin_range_v":[-1,1],"gate_range_v":[-1,1]}]})
    return catalog


def load_scene(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or not isinstance(data.get("channels"),list):
        raise ValueError("场景文件必须包含 channels 列表")
    return data


def save_scene(path,scene):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(scene,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def available_ports():
    """Return device/description pairs; Windows registry also works before pyserial install."""
    try:
        from serial.tools import list_ports
        return sorted([(p.device,p.description or p.device) for p in list_ports.comports()],
                      key=lambda p:p[0].lower())
    except ImportError:
        if sys.platform!="win32": return []
        try:
            import winreg
            key=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DEVICEMAP\SERIALCOMM")
            found=[]; index=0
            while True:
                try: name,device,_=winreg.EnumValue(key,index)
                except OSError: break
                found.append((device,name)); index+=1
            winreg.CloseKey(key)
            return sorted(found,key=lambda p:p[0].lower())
        except OSError: return []


def probe_device(port_name,baud=115200,serial_factory=None):
    """Expect STATUS=03 for an unknown command. The FPGA performs no SPI writes."""
    if serial_factory is None:
        try: import serial
        except ImportError: raise ValueError("检测和发送需要 pyserial：python -m pip install pyserial")
        serial_factory=serial.Serial
    probe=frame(0xa5,0x7f)
    with serial_factory(port_name,baud,timeout=2,bytesize=8,parity="N",stopbits=1) as port:
        port.reset_input_buffer()
        port.write(probe); port.flush()
        reply=port.read(8)
        if not reply:
            raise ValueError(
                "{} 可以打开，但发送探测指令后 2 秒内未收到任何回包。"
                "请检查 FPGA 是否已下载包含串口模块的新 bitstream、UART 引脚约束、"
                "PC TX→FPGA RX / FPGA TX→PC RX 接线及共地（115200 8N1）。".format(port_name)
            )
        status=decode_reply(reply,0xa5,0x7f)
    if status!=3:
        raise ValueError("设备返回 {}；预期未知指令 03".format(STATUS.get(status,status)))
    return "已检测到 AD9106 指令解析器：{} @ {} 8N1".format(port_name,baud)
