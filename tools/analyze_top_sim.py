"""Export evidence from the completed functional-clock top-level regression."""
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    sim = root / ".uart_sim/top_fast"
    output = root / "docs/verification"
    output.mkdir(parents=True, exist_ok=True)
    log = (sim / "tb_top_uart.log").read_text(encoding="utf-8", errors="replace")
    if "PASS TOP SUMMARY: 15 replies; 2 initializations;" not in log:
        raise RuntimeError("Top regression has not completed successfully")
    if "Fatal:" in log:
        raise RuntimeError("Simulation contains a fatal error")
    with (sim / "top_events.csv").open(newline="") as stream:
        events = list(csv.DictReader(stream))
    with (sim / "top_spi_writes.csv").open(newline="") as stream:
        spi = list(csv.DictReader(stream))
    results = []
    fig, axes = plt.subplots(4, 1, figsize=(10, 8), constrained_layout=True)
    for ax, rate in zip(axes, [100, 200, 300, 74200]):
        source = sim / ("square_{}khz.csv".format(rate))
        with source.open(newline="") as stream:
            data = list(csv.DictReader(stream))
        samples = [int(row["dac_sram_code"]) for row in data]
        times = [float(row["time_us"]) for row in data]
        assert len(samples) == 1485
        high = max(samples)
        cycles = sum(samples[i] == high and samples[i-1] != high for i in range(len(samples)))
        measured_khz = cycles * 100
        assert measured_khz == rate
        results.append({"frequency_khz": rate, "samples": len(samples), "cycles_per_10us": cycles,
                        "high_percent": sum(v == high for v in samples) * 100 / 1485})
        ax.step(times, samples, where="post", color="#136f8a", linewidth=1.5)
        ax.set_xlim(0, 0.2 if rate == 74200 else 10)
        ax.set_ylim(-2300, 2300)
        ax.set_title("{} kHz | {} cycles / 10 us{}".format(
            rate, cycles, " | first 0.2 us shown" if rate == 74200 else ""), fontsize=10, loc="left")
        ax.set_ylabel("SRAM code")
        ax.grid(alpha=0.2)
        shutil.copyfile(source, output / source.name)
    axes[-1].set_xlabel("Time at 148.5 MHz DAC sample clock (us)")
    fig.suptitle("Captured SPI-loaded square-wave samples\nDigital codes before gain/offset; not an analog DAC model", fontsize=12)
    fig.savefig(str(output / "square_samples.png"), dpi=160)
    plt.close(fig)

    shutil.copyfile(sim / "top_events.csv", output / "top_events.csv")
    shutil.copyfile(sim / "top_spi_writes.csv", output / "top_spi_writes.csv")
    shutil.copyfile(sim / "tb_top_uart.log", output / "top_functional_clock.txt")
    shutil.copyfile(root / ".uart_sim/uart_control.log", output / "module_regression.txt")
    shutil.copyfile(root / ".uart_sim/clock_vendor/tb_clock_wizard.log", output / "vendor_clock.txt")
    for source, dest in [("io_drc.rpt", "io_drc.txt"), ("timing.rpt", "synthesis_timing.txt"),
                         ("utilization.rpt", "synthesis_utilization.txt")]:
        shutil.copyfile(root / ".uart_sim/top_synth" / source, output / dest)
    files = list((root / "AD9106_demo.srcs/sources_1/new").glob("*.v"))
    files += [root / "AD9106_demo.srcs/sources_1/bd/design_1/design_1.bd",
              root / "AD9106_demo.gen/sources_1/bd/design_1/sim/design_1.v",
              root / "AD9106_demo.gen/sources_1/bd/design_1/hdl/design_1_wrapper.v"]
    files += list((root / "AD9106_demo.srcs/sim_1/new").glob("*.sv"))
    summary = {
        "profile": "actual generated top, production parameters, functional clock model",
        "simulated_time_ms": float(events[-1]["time_ns"]) / 1000000,
        "reply_checks": sum(row["event"] == "reply" for row in events),
        "initialization_checks": sum(row["event"] == "init" for row in events),
        "captured_spi_writes_including_reset_test": len(spi),
        "square_tests": results,
        "latency_lines": re.findall(r"PASS TOP: reply[^\n]*", log),
        "source_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in files},
        "limits": ["Functional clock run does not verify MMCM analog behavior.",
                   "SPI checking and SRAM reconstruction do not verify DAC analog output.",
                   "UART pin/IOSTANDARD constraints are missing; see io_drc.txt."]}
    prefix = output / "vendor_top_prefix.txt"
    if prefix.exists():
        vendor_text = prefix.read_text(encoding="utf-8", errors="replace")
        summary["vendor_prefix"] = {
            "scope": "init, sine, triangle, 100 kHz square passed; remaining long vendor run intentionally stopped",
            "pass_lines": re.findall(r"PASS TOP:[^\n]*", vendor_text)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PASS: exported {} replies, {} initializations, {} physical SPI writes and four waveform plots".format(
        summary["reply_checks"], summary["initialization_checks"], len(spi)))


if __name__ == "__main__":
    main()
