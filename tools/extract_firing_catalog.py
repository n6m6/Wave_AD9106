"""Extract every topology/mode/experiment from the user's offline HTML."""
import hashlib
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODE_NAMES = [
    "Tonic spiking", "Phasic spiking", "Tonic bursting", "Phasic bursting", "Mixed mode",
    "Spike frequency adaptation", "Class I excitability", "Class II excitability", "Spike latency",
    "Subthreshold oscillations", "Resonator", "Integrator", "Rebound spike", "Rebound burst",
    "Threshold variability", "Bistability", "Depolarizing after-potential", "Accommodation",
    "Inhibition-induced spiking", "Inhibition-induced bursting", "All-or-none response",
    "Refractory period", "Depolarization block"]


def plain(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def limits(text, signal):
    match = re.search(signal + r"=([+\-\d.]+)～([+\-\d.]+)\s*V", text)
    if not match:
        raise ValueError("Missing voltage range: " + text)
    return [float(match[1]), float(match[2])]


def components(mode):
    return {12: ["sequence", "near", "far", "single"],
            15: ["sequence", "low", "mid", "high"],
            21: ["sequence", "low", "mid", "high"],
            22: ["pair", "first", "second"]}.get(mode, ["default"])


def families(mode, topology):
    vin = {7: "ramp_hold", 11: "pulse_train", 12: "near_far_pulses", 13: "negative_release",
           14: "negative_release", 18: "fast_slow_ramp", 19: "negative_window",
           20: "negative_bursts", 21: "multi_level_pulses", 22: "paired_probes",
           23: "ramp_hold"}.get(mode, "positive_window")
    gate = {3: "three_gate_windows", 4: "onset_gate_window", 5: "ramp_or_step_hold",
            6: "ramp", 10: "sine_bias", 11: "sine_or_gate_window",
            15: "three_gate_levels", 16: "stop_gate_step", 18: "constant_or_window"}.get(mode, "constant")
    if mode==12 and topology==6: gate="constant_with_synchronous_notches"
    if mode==11 and topology==7: gate="gate_windows_or_constant"
    return {"vin": vin, "gate": gate}


def extract(source):
    text = source.read_text(encoding="utf-8-sig")
    entries = []
    pattern = r'<details\s+id="t(3|5|6|7)m(\d+)">(.*?)</details>'
    for match in re.finditer(pattern, text, re.S):
        topology, mode, block = int(match[1]), int(match[2]), match[3]
        title_match = re.search(r"<summary>(.*?)</summary>", block, re.S)
        paragraphs = re.findall(r"<p>(.*?)</p>", block, re.S)
        description, cases = [], []
        for paragraph in paragraphs:
            label_match = re.search(r"<b>(.*?)</b>", paragraph, re.S)
            if not label_match:
                description.append(plain(paragraph)); continue
            label = plain(label_match[1])
            experiment = re.search(r"\b(0[3567]_[A-Za-z0-9_.\-]+)", label)
            if not experiment:
                raise ValueError("Unrecognized experiment label: " + label)
            parameter_text = plain(paragraph.split("<br>", 1)[1].split("<br>", 1)[0])
            cases.append({"variant": len(cases), "experiment": experiment[1], "label": label,
                          "parameters": parameter_text, "vin_range_v": limits(parameter_text, "Vin"),
                          "gate_range_v": limits(parameter_text, "Gate")})
        entries.append({"topology": topology, "mode": mode, "name": MODE_NAMES[mode-1],
                        "source_anchor": "t{}m{}".format(topology, mode), "title": plain(title_match[1]),
                        "description": " ".join(description), "families": families(mode, topology),
                        "components": components(mode), "cases": cases})
    assert len(entries) == 92
    assert {(e["topology"], e["mode"]) for e in entries} == {(t,m) for t in (3,5,6,7) for m in range(1,24)}
    assert all(e["cases"] for e in entries)
    return {"source": str(source.relative_to(ROOT)), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "fidelity": "Graph/text-derived parameterized templates; original CSV/PWL timing is not included.",
            "topologies": [3,5,6,7], "modes": entries}


def main():
    sources = list((ROOT / "AD9106_demo.srcs/sources_1/new").glob("*23*.html"))
    if len(sources) != 1:
        raise RuntimeError("Expected one user HTML reference containing 23 in its name")
    catalog = extract(sources[0])
    output = ROOT / "waveforms"
    output.mkdir(exist_ok=True)
    (output / "firing_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 23 种发放模式的 Vin / Vgate 分类", "",
             "从用户提供的 HTML 自动提取，包含 4 种拓扑 × 23 种模式及全部主例/对照。实验是否产生目标发放，以原文判定为准；本工程生成的是输入激励。",
             "", "variant 从 0 开始；不同实验曲线分别编号。sequence 表示同一输入中的多幅度/近远间隔序列；low/mid/high、near/far/single、first/second 可分别选择。",
             "", "原始 CSV、RAW、input.json 未随 HTML 提供。默认时序为图文重建模板，不能声称精确重现实验。", ""]
    for entry in catalog["modes"]:
        lines += ["## 拓扑 {} / {:02d} {}".format(entry["topology"], entry["mode"], entry["name"]), "",
                  entry["title"], "", entry["description"], "",
                  "Vin：`{}`；Vgate：`{}`；分项：`{}`。".format(entry["families"]["vin"], entry["families"]["gate"], ", ".join(entry["components"])), "",
                  "| variant | 实验 / 对照 | Vin / V | Vgate / V |", "|---:|---|---|---|"]
        for case in entry["cases"]:
            lines.append("| {} | {} | {} | {} |".format(case["variant"],case["label"],case["vin_range_v"],case["gate_range_v"]))
        lines.append("")
    (ROOT / "docs/FIRING_CATALOG.md").write_text("\n".join(lines), encoding="utf-8")
    cases = sum(len(e["cases"]) for e in catalog["modes"])
    print("Extracted 92 topology/mode entries, {} experiment variants, {} Vin/Gate selections".format(cases,cases*2))


if __name__ == "__main__":
    main()
