"""Nonvisual serial/scene helpers for the AD9106 desktop controller."""
import json
import sys
from pathlib import Path

from ad9106_firing import ROOT, STATUS, frame, decode_reply


def load_catalog():
    catalog=json.loads((ROOT/"waveforms/firing_catalog.json").read_text(encoding="utf-8"))
    for entry in catalog["modes"]:
        if entry["mode"]==12:
            entry["description"]="Vin 快脉冲、慢脉冲分开测试：选择一个实验变体，设置内部方波单周期时长、占空比和脉冲数量。Vgate 恒压。"
            source=entry["cases"][0]
            entry["components"]=["default"]
            entry["cases"]=[dict(source,variant=i,experiment=group+"_pulses",source_experiment=source["experiment"],label=label,pulse_group=group,
                                 gate_range_v=[source["gate_range_v"][1]]*2)
                            for i,group,label in ((0,"near","快脉冲"),(1,"far","慢脉冲"))]
        if entry["mode"]==11:
            entry["description"]="Vin 方波用周期时长与占空比设置，Vgate 连续正弦用频率设置。正弦最高点与首个 Vin 方波中心对齐；同周期时每个脉冲均对齐。配对通道的实验变体同步切换。"
        if entry["mode"] in (5,7):
            entry["description"]=("Vgate 两段方波" if entry["topology"]==7 else "Vgate 斜坡接保持平台") if entry["mode"]==5 else "Vin 斜坡接保持平台，Vgate 恒压"
            entry["description"]+="；两段电压、两段持续时间独立设置。"
        if entry["mode"]==6:
            entry["description"]="Vgate 斜坡：开始电压、结束电压和持续时间可调；Vin 为方波窗口。"
        if entry["mode"]==23:
            entry["name"]="Excitability block"
            entry["title"]="23 兴奋性阻断"
    for topology in (3,5,6,7):
        catalog["modes"].append({"topology":topology,"mode":24,"name":"Static scan",
            "description":"单次有限脉冲：Vgate 提前建立、延后归零，包住 Vin；长平台由 FPGA 定时，结束后全部归零。",
            "components":["pulse"],"cases":[{"variant":0,"experiment":"static_scan",
            "vin_range_v":[0,1],"gate_range_v":[0,1]}]})
        for mode,name,description in ((25,"square","FPGA 定时方波：幅值为中心到峰值，偏移为中心电压，占空比可调；过短切换间隔会拒绝。"),
                                      (26,"sine","芯片 DDS 正弦波：频率、幅值、电压偏移、时间偏移可调；多路正弦共用频率，显示量化后实际频率。")):
            catalog["modes"].append({"topology":topology,"mode":mode,"name":name,
                "description":description,"components":[name],"cases":[{"variant":0,"experiment":name,
                "vin_range_v":[-1,1],"gate_range_v":[-1,1]}]})
    from firing_waveforms import constant_output, PERIOD_US
    for entry in catalog["modes"]:
        topology,mode=entry["topology"],entry["mode"]
        reference=PERIOD_US.get(mode,100)
        if mode==9: reference={3:60,5:100,6:225,7:50}[topology]
        if mode==11 and topology in (6,7): reference={6:60,7:120}[topology]
        if mode==12 and topology==6: reference=210
        entry["reference_period_us"]=reference
        for case in entry["cases"]:
            case["constant_signals"]=[] if mode==24 else [signal for signal in ("vin","gate") if constant_output(topology,mode,signal,case)]
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
