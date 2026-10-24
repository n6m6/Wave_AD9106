"""Check captured SPI SRAM/registers and plot their nominal DAC output sequences."""
import argparse
import csv
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from firing_waveforms import make_waveform

ROOT=Path(__file__).resolve().parents[1]


def signed12(value):
    value &= 4095
    return value-4096 if value & 2048 else value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim",type=Path,default=ROOT/".uart_sim/firing_top")
    parser.add_argument("--fixture",type=Path,default=ROOT/".uart_sim/firing_scene_fixture")
    parser.add_argument("--out",type=Path,default=ROOT/"docs/firing_verification")
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    plan=json.loads((args.fixture/"plan.json").read_text(encoding="utf-8"))
    raw=(args.sim/"observed_sram.mem").read_text().split()
    regs=[None if "x" in s.lower() else int(s,16) for s in (args.sim/"observed_registers.mem").read_text().split()]
    assert len(raw)==4096 and len(regs)==128
    expected_regs={a:v for a,v in plan["spi_oracle"] if a<128}
    # Finite pattern ends in the chip; FPGA leaves RUN set after playback.
    expected_regs[0x1e]=1
    for address,value in expected_regs.items():
        assert regs[address]==value,"Captured register {:04x} differs".format(address)
    with (args.sim/"firing_spi.csv").open() as stream:
        captured=list(csv.DictReader(stream))
    assert len(captured)==len(plan["spi_oracle"])
    assert [(int(r["address_hex"],16),int(r["data_hex"],16)) for r in captured]==[tuple(w) for w in plan["spi_oracle"]]
    hold=(regs[0x28]>>8)&15; hold=hold or 16
    period_base=(regs[0x28]>>4)&15; period_base=period_base or 16
    ticks=regs[0x29]*period_base
    assert ticks==plan["pattern_ticks"] and hold==plan["hold"]
    summary=dict(frames=len(plan["packets"]),captured_spi_writes=len(captured),
                 frame_frequency_hz=plan["dac_clock_hz"]/ticks,hold=hold,
                 allocated_sram_words=plan["sram_words"],channels=[])
    fig,axes=plt.subplots(4,1,figsize=(12,8),sharex=True)
    for c,ax in zip(plan["channels"],axes):
        ch=c["channel"]; delay=0x5c-4*(ch-1)
        start=regs[delay+1]>>4; stop=regs[delay+2]>>4
        assert regs[delay]==0 and regs[0x36-ch]==0x4000 and regs[0x26-ch]==0
        assert start==c.get("start",0) and stop==c.get("stop",0)
        if c["source"]=="sram":
            codes=[signed12(int(v,16)) for v in raw[start:stop+1]]
            assert codes==c["samples"],"Captured DAC{} SRAM differs".format(ch)
            assert len(codes)+c.get("zero_tail_samples",0)==plan["samples_per_frame"]
            codes=codes+[0]*c.get("zero_tail_samples",0)
        else:
            codes=[signed12(regs[0x32-ch]>>4)]*plan["samples_per_frame"]
            assert codes[0]==c["constant_code"]
        times=[i*hold/plan["dac_clock_hz"]*1e6 for i in range(len(codes))]
        volts=[plan["zero_code_v"]+v*plan["full_scale_v"]/2048 for v in codes]
        ax.step(times,volts,where="post",linewidth=1.2)
        ax.set_ylabel("DAC{} / V*".format(ch)); ax.grid(alpha=.25)
        ax.set_title("T{} mode {:02d} {} | envelope {:g} kHz | SRAM {}..{}".format(
            c.get("topology","-"),c.get("mode",0),c.get("signal","off"),
            c["frequency_hz"]/1000,start,stop),fontsize=10,loc="left")
        summary["channels"].append(dict(channel=ch,start=start,stop=stop,samples=len(codes),
            cycles_per_frame=c.get("cycles_per_frame",0),envelope_frequency_hz=c["frequency_hz"],
            min_code=min(codes),max_code=max(codes),nominal_min_v=min(volts),nominal_max_v=max(volts)))
    axes[-1].set_xlabel("Time within programmed common frame / us")
    fig.suptitle("Reconstructed from SPI captured at the generated top-level pins\n* Nominal bipolar conversion; not an analog circuit simulation",fontsize=12)
    fig.tight_layout(rect=(0,0,1,.93)); fig.savefig(args.out/"four_channel_spi_reconstruction.png",dpi=160); plt.close(fig)
    summary["result"]="PASS: every programmed register and all allocated samples match captured SPI"
    (args.out/"observed_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    for filename in ("firing_uart.log","firing_spi.csv"):
        shutil.copyfile(args.sim/filename,args.out/filename)

    # Template overview is deliberately labelled separately from captured RTL data.
    catalog=json.loads((ROOT/"waveforms/firing_catalog.json").read_text(encoding="utf-8"))
    fig,axes=plt.subplots(6,4,figsize=(16,18))
    for mode,ax in enumerate(axes.flat,1):
        if mode>23: ax.axis("off"); continue
        for signal,color in (("vin","#1761a0"),("gate","#cf6900")):
            wave,entry,_=make_waveform(catalog,dict(topology=6,mode=mode,signal=signal))
            times=[i/4000 for i in range(4001)]
            ax.plot(times,[wave.value(t) for t in times],label=signal,color=color,linewidth=.9)
        ax.set_title("{:02d} {}".format(mode,entry["name"]),fontsize=9)
        ax.set_xlim(0,1); ax.grid(alpha=.2); ax.tick_params(labelsize=8)
        if mode==1: ax.legend(fontsize=8)
        if mode>=21: ax.set_xlabel("Envelope phase")
    fig.suptitle("Topology 6: 23 graph/text-derived input templates (default variant)\nReference volts before amplitude scaling; inferred timings; not original experiment data",fontsize=13)
    fig.tight_layout(rect=(0,0,1,.96)); fig.savefig(args.out/"topology6_template_overview.png",dpi=160); plt.close(fig)
    print(summary["result"])


if __name__=="__main__": main()
