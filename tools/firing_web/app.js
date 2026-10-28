"use strict";

const el=id=>document.getElementById(id);
const modesZh=["持续放电","起始放电","持续簇发","起始簇发","混合模式","频率适应", "I 类兴奋性","II 类兴奋性","发放延迟","阈下振荡","共振器","积分器", "反跳单发","反跳簇发","阈值可变性","双稳态","去极化后电位","适应性", "抑制诱发放电","抑制诱发簇发","全或无","不应期","兴奋性阻断"];
const paramLabels={period_us:"模板长度 / us",start_us:"开始时刻 / us",width_us:"脉冲宽度 / us",rise_us:"上升沿 / us",fall_us:"下降沿 / us",ramp_us:"斜坡时长 / us",gap_us:"双脉冲间隔 / us",pulse_period_us:"脉冲列间隔 / us",pulse_count:"脉冲列数量",gate_sine_period_us:"Gate 正弦周期 / us",gate_floor_v:"Gate 最低电压 / V",gate_initial_v:"Gate 初始电压 / V",gate_final_v:"Gate 末段电压 / V",gate_baseline_v:"Gate 基线电压 / V",levels_v:"三档电压 / V（逗号分隔）"};
const extraLabels={rhythm_on_us:"Vin ON 时间 / μs",rhythm_frequency_khz:"Vgate 频率 / kHz",
  rhythm_duty_percent:"本路方波占空比 / %",rhythm_phase_deg:"本路初始相位 / °",
  vin_width_us:"Vin 脉宽（含边沿）/ μs",gate_width_us:"Vgate 脉宽（含边沿）/ μs",
  width_us:"Vin 脉冲持续时间 / μs",gate_lead_us:"Vgate 提前建立 / μs",gate_tail_us:"Vgate 延后归零 / μs",
  rise_time_us:"本路上升时间（0～1）/ μs",fall_time_us:"本路下降时间（0～1）/ μs",
  pulse_gap_us:"脉冲间隔（回到基线后）/ μs",vin_period_us:"Vin 方波单周期时长 / μs",
  vin_duty_percent:"Vin 内部方波占空比 / %",gate_frequency_khz:"Vgate 正弦频率 / kHz",
  pulse_count:"脉冲数量",gate_initial_v:"Vgate 开始电压 / V",gate_final_v:"Vgate 结束电压 / V",
  stage1_voltage_v:"第一段电压 / V",stage2_voltage_v:"第二段电压 / V",
  first_stage_us:"第一段持续时间 / μs",second_stage_us:"第二段持续时间 / μs",
  level_low_v:"第一档电压 / V",level_mid_v:"第二档电压 / V",level_high_v:"第三档电压 / V"};
const extraKeys=Object.keys(extraLabels);
Object.assign(paramLabels,extraLabels);
const state={catalog:null,scene:null,connectedPort:null,preview:null,previewTimer:null,previewToken:0,busy:false,jobId:null,portTimer:null};
paramLabels.duty_percent="方波占空比 / %";
const rhythmMode=mode=>[27,28].includes(Number(mode));
const rhythmActive=()=>[...document.querySelectorAll('.channel-card')].some(card=>card.querySelector('[data-field="enabled"]').checked&&rhythmMode(card.querySelector('[data-field="mode"]').value));

async function api(route,body){
  const options=body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)};
  const response=await fetch(route,options);
  let result;
  try{result=await response.json()}catch{throw new Error(`服务返回非 JSON：${response.status}`)}
  if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
  return result;
}

function log(text,kind=""){
  const box=el("activityLog"),row=document.createElement("div");
  row.className=kind; row.textContent=`${new Date().toLocaleTimeString("zh-CN",{hour12:false})}  ${text}`;
  box.prepend(row);
  while(box.children.length>18)box.removeChild(box.lastChild);
}

function entry(topology,mode){return state.catalog.modes.find(e=>e.topology===Number(topology)&&e.mode===Number(mode))}
function constantBinding(binding){
  const e=entry(binding.topology,binding.mode);
  const c=e?.cases.find(c=>String(c.variant)===String(binding.variant??0)||c.experiment===binding.variant);
  return Boolean(c?.constant_signals?.includes(binding.signal));
}
function constantCard(card){
  const f=name=>card.querySelector(`[data-field="${name}"]`).value;
  return constantBinding({topology:f("topology"),mode:f("mode"),variant:f("variant"),signal:f("signal")});
}
function option(select,value,label){const node=document.createElement("option");node.value=String(value);node.textContent=label;select.append(node)}
function choose(select,desired){
  const exists=[...select.options].some(o=>o.value===String(desired));
  select.value=exists?String(desired):select.options[0]?.value||"";
}
function peakFor(ch){
  const e=entry(ch.querySelector('[data-field="topology"]').value,ch.querySelector('[data-field="mode"]').value);
  const variant=Number(ch.querySelector('[data-field="variant"]').value);
  const signal=ch.querySelector('[data-field="signal"]').value;
  const range=e.cases.find(c=>c.variant===variant)?.[`${signal}_range_v`]||[0,0];
  return Math.min(10,Math.max(...range.map(Math.abs)));
}

function reciprocalDuration(value,scale,label){
  const parsed=number(value,label);
  if(parsed<=0)throw new Error(`${label}必须大于 0`);
  return scale/parsed;
}

function durationBinding(binding){
  // Migrate only legacy fields. Actual time parameters must not be rescaled.
  const result={...binding,parameters:{...(binding.parameters||{})}};
  if(rhythmMode(binding.mode))return {...result,duration_us:binding.duration_us??200,time_offset_us:0};
  if(constantBinding(binding))return {...result,duration_us:10,time_offset_us:0,parameters:{}};
  const old=binding.frequency_hz;
  if(result.duration_us===undefined)
    result.duration_us=reciprocalDuration(old??(Number(binding.mode)>=25?1000:100000),1e6,"旧场景时序参数");
  else if(old!==undefined&&Math.abs(Number(result.duration_us)*Number(old)/1e6-1)>1e-12)
    throw new Error("时长与旧版频率字段不一致，请仅保留 duration_us");
  delete result.frequency_hz;
  if(binding.phase_deg!==undefined){
    const offset=-number(binding.phase_deg,"旧相位")*result.duration_us/360;
    if(result.time_offset_us!==undefined&&Math.abs(Number(result.time_offset_us)-offset)>1e-10+Math.abs(offset)*1e-12)
      throw new Error("时间偏移与旧相位不一致，请仅保留时间偏移");
    result.time_offset_us=offset;
  }
  delete result.phase_deg;
  if(Number(binding.mode)===24){
    result.time_offset_us=0;
    if(binding.signal==="gate"&&!state.scene?.static_pulse){
      result.parameters.gate_lead_us??=result.parameters.start_us??10;
      result.parameters.gate_tail_us??=10;
    }
  }
  const reference=result.parameters.period_us??entry(binding.topology,binding.mode)?.reference_period_us;
  if(reference)for(const [old,current] of [["rise_us","rise_time_us"],["fall_us","fall_time_us"]]){
    if(result.parameters[old]!==undefined){
      if(result.parameters[current]===undefined)result.parameters[current]=Number(result.parameters[old])*result.duration_us/reference;
      delete result.parameters[old];
    }
  }
  for(const [legacy,current] of [["vin_frequency_khz","vin_period_us"]]){
    if(result.parameters[legacy]===undefined)continue;
    const duration=reciprocalDuration(result.parameters[legacy],1000,"旧场景内部时序参数");
    if(result.parameters[current]!==undefined&&Math.abs(Number(result.parameters[current])/duration-1)>1e-12)
      throw new Error("新旧内部周期设置不一致，请仅保留时长参数");
    result.parameters[current]=duration;
    delete result.parameters[legacy];
  }
  let sinePeriod=result.parameters.gate_period_us;
  if(sinePeriod===undefined&&result.parameters.gate_sine_period_us!==undefined&&[10,11].includes(Number(binding.mode)))
    sinePeriod=Number(result.parameters.gate_sine_period_us)*result.duration_us/reference;
  if(sinePeriod!==undefined){
    const frequency=reciprocalDuration(sinePeriod,1000,"旧场景正弦周期");
    if(result.parameters.gate_frequency_khz!==undefined&&Math.abs(Number(result.parameters.gate_frequency_khz)/frequency-1)>1e-12)
      throw new Error("正弦频率与旧周期不一致，请只保留一种设置");
    result.parameters.gate_frequency_khz=frequency;
    delete result.parameters.gate_period_us;delete result.parameters.gate_sine_period_us;
  }
  return result;
}

function createEditor(number,binding){
  binding=durationBinding(binding);
  const card=document.createElement("article");card.className="channel-card";card.dataset.channel=number;
  card.innerHTML=`<div class="channel-top"><div class="channel-name"><span class="channel-icon">${String(number).padStart(2,"0")}</span>DAC${number}</div><label class="switch-label"><input type="checkbox" data-field="enabled">启用通道</label></div>
    <div class="channel-grid">
      <div class="field"><label>拓扑</label><select data-field="topology"></select></div>
      <div class="field"><label>模式</label><select data-field="mode"></select></div>
      <div class="field"><label>输入信号</label><select data-field="signal"><option value="vin">Vin</option><option value="gate">Vgate</option></select></div>
      <div class="field"><label>同步配对</label><select data-field="pair"><option value="">无</option><option value="A">A</option><option value="B">B</option></select></div>
      <div class="field wide"><label>实验变体 · 同图不同曲线逐一编号</label><select data-field="variant"></select></div>
      <div class="field"><label>序列分段</label><select data-field="component"></select></div>
      <div class="field"><label>整组时窗时长 / μs</label><input data-field="duration" type="number" min="0.001" step="any" inputmode="decimal"></div>
      <div class="field"><label>幅值 / V（绝对峰值）</label><div class="inline"><input data-field="amplitude" type="number" min="0" max="10" step="any"><button class="reference-button" data-action="peak" type="button">原图幅值</button></div></div>
      <div class="field"><label>电压偏移 / V</label><input data-field="offset" type="number" step="any"></div>
      <div class="field"><label>时间偏移 / μs</label><input data-field="timeShift" type="number" step="any"><small>正数延后，负数提前；循环平移</small></div>
    </div><p class="pair-note" role="status"></p><p class="channel-note"></p><div class="simple-params advanced-grid"></div><p class="simple-hint channel-note"></p><details class="advanced"><summary>高级时序参数</summary><div class="advanced-grid"></div></details>`;
  const field=name=>card.querySelector(`[data-field="${name}"]`);
  for(const t of [3,5,6,7])option(field("topology"),t,`拓扑 ${t}`);
  for(let m=1;m<=23;m++)option(field("mode"),m,`${String(m).padStart(2,"0")} ${modesZh[m-1]}`);
  option(field("mode"),24,"24 静态扫描（单次脉冲 / Vgate 包络）");
  option(field("mode"),25,"25 标准方波（支持 1000 μs 单周期）");
  option(field("mode"),26,"26 标准正弦（支持 1 kHz）");
  option(field("mode"),27,"27 节律调制 · Vin 方波 / Vgate 正弦");
  option(field("mode"),28,"28 节律调制 · Vin / Vgate 双方波");
  const advanced=card.querySelector(".advanced .advanced-grid");
  for(const [key,label] of Object.entries(paramLabels)){
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=label;
    const input=document.createElement("input");input.dataset.param=key;input.type="text";
    input.placeholder=key==="levels_v"?"例如 3, 4.7, 5":"模板默认";
    if(extraKeys.includes(key)){
      input.type="number";input.step="any";input.placeholder="留空沿用原模板";
      input.setAttribute("aria-label",label);
      if(!key.endsWith("_v")&&key!=="rhythm_phase_deg")input.min="0";
      if(key==="rhythm_duty_percent")input.max="100";
      if(key==="pulse_count"){input.min="1";input.max="1000";input.step="1"}
      if(key==="vin_duty_percent")input.max="100";
      if(key==="rise_time_us"||key==="fall_time_us")input.max="1";
    }
    wrap.append(lab,input);(extraKeys.includes(key)?card.querySelector(".simple-params"):advanced).append(wrap);
  }
  field("enabled").checked=binding.enabled!==false;
  choose(field("topology"),binding.topology??6);choose(field("mode"),binding.mode??3);
  choose(field("signal"),binding.signal??"vin");choose(field("pair"),binding.pair??"");
  updateVariantChoices(card,binding.variant??0,binding.component);
  field("duration").value=Number(binding.mode)===26?1000/binding.duration_us:binding.duration_us;
  field("amplitude").value=binding.amplitude_v??(rhythmMode(binding.mode)?0.5:peakFor(card));
  field("offset").value=binding.offset_v??(rhythmMode(binding.mode)?0.5:0);field("timeShift").value=binding.time_offset_us??0;
  for(const input of card.querySelectorAll("[data-param]")){
    const val=binding.parameters?.[input.dataset.param];
    if(val!==undefined)input.value=Array.isArray(val)?val.join(", "):val;
  }
  updateSimpleControls(card);
  card.dataset.previousMode=field("mode").value;
  card.classList.toggle("disabled",!field("enabled").checked);
  return card;
}

function updateVariantChoices(card,wantedVariant=0,wantedComponent=null){
  const field=name=>card.querySelector(`[data-field="${name}"]`);
  const e=entry(field("topology").value,field("mode").value);
  if(!e)return;
  const v=field("variant");v.replaceChildren();
  for(const c of e.cases){
    option(v,c.variant,`${c.variant} · ${c.pulse_group?c.label:c.experiment}  |  Vin ${c.vin_range_v[0]}…${c.vin_range_v[1]} V · Gate ${c.gate_range_v[0]}…${c.gate_range_v[1]} V`);
  }
  if(typeof wantedVariant==="string"&&isNaN(Number(wantedVariant))){
    wantedVariant=e.cases.find(c=>c.experiment===wantedVariant)?.variant??0;
  }
  choose(v,wantedVariant);
  const c=field("component");c.replaceChildren();
  for(const part of e.components)option(c,part,part);
  choose(c,wantedComponent??e.components[0]);
  card.querySelector(".channel-note").textContent=e.description||"图文重建模板";
  const mode=Number(field("mode").value),basic=mode===25||mode===26;
  for(const name of ["topology","variant","component"])field(name).closest(".field").hidden=basic;
  if(mode===12)field("component").closest(".field").hidden=true;
  card.querySelector(".advanced summary").textContent=mode===25?"方波参数":"高级时序参数";
  field("duration").closest(".field").querySelector("label").textContent=mode===26?"正弦频率 / kHz":basic?"单周期时长 / μs":"整组时窗时长 / μs";
  field("timeShift").disabled=false;
  card.querySelector(".advanced").hidden=mode===26;
  for(const input of card.querySelectorAll("[data-param]"))
    input.closest(".field").hidden=basic?!(mode===25&&input.dataset.param==="duty_percent"):input.dataset.param==="duty_percent";
  if(mode===25){
    const duty=card.querySelector('[data-param="duty_percent"]');if(!duty.value)duty.value=50;
    card.querySelector(".advanced").open=true;
  }
  if(Number(field("mode").value)===24){
    const isVin=field("signal").value==="vin";
    card.querySelector('[data-action="peak"]').hidden=true;
    field("amplitude").closest(".field").querySelector("label").textContent=isVin?"Vin 脉冲电压 / V":"Vgate 包络电压 / V";
    card.querySelector(".channel-note").textContent=isVin?
      "本通道输出一次 Vin 脉冲，保持设定时间后自动归零。":
      "Vgate 提前建立、延后归零，包住配对的 Vin 脉冲。";
    card.querySelector(".advanced").open=true;
    field("duration").closest(".field").hidden=true;
    for(const [name,value] of [["width_us",2000],["gate_lead_us",300],["gate_tail_us",300]]){
      const input=card.querySelector(`[data-param="${name}"]`);
      if(!input.value)input.value=value;
    }
    for(const name of ["start_us","width_us"])
      card.querySelector(`[data-param="${name}"]`).closest(".field").hidden=!isVin;
  }else{
    card.querySelector('[data-action="peak"]').hidden=false;
    field("duration").closest(".field").hidden=false;
    field("amplitude").closest(".field").querySelector("label").textContent="幅值 / V（绝对峰值）";
    for(const name of ["start_us","width_us"])
      card.querySelector(`[data-param="${name}"]`).closest(".field").hidden=basic;
    if(basic){
      card.querySelector('[data-action="peak"]').hidden=true;
      field("amplitude").closest(".field").querySelector("label").textContent="幅值 / V（中心到峰值）";
    }
  }
  updateSimpleControls(card);
}

function updateSimpleControls(card){
  const field=name=>card.querySelector(`[data-field="${name}"]`);
  const mode=Number(field("mode").value),topology=Number(field("topology").value),vin=field("signal").value==="vin";
  const firing=mode<24,levels=(mode===15&&!vin)||(mode===21&&vin),stages=(mode===5&&!vin)||(mode===7&&vin);
  const hasGateWidth=[3,4,6,15,16].includes(mode)||(mode===18&&topology!==3);
  const hasEdges=mode<=24&&!constantCard(card)&&!(mode===10&&!vin)&&!(mode===11&&!vin);
  const visible={width_us:mode===24&&vin,gate_lead_us:mode===24&&!vin,gate_tail_us:mode===24&&!vin,
    rise_time_us:hasEdges,fall_time_us:hasEdges,
    vin_width_us:firing&&vin&&![7,11,12].includes(mode),gate_width_us:firing&&!vin&&hasGateWidth,
    pulse_gap_us:(mode===3&&!vin)||([20,22].includes(mode)&&vin),vin_period_us:[11,12].includes(mode)&&vin,
    vin_duty_percent:[11,12].includes(mode)&&vin,gate_frequency_khz:[10,11].includes(mode)&&!vin,
    pulse_count:(mode===3&&!vin)||([11,12,20].includes(mode)&&vin),
    gate_initial_v:mode===6&&!vin,gate_final_v:mode===6&&!vin,
    stage1_voltage_v:stages,stage2_voltage_v:stages,first_stage_us:stages,second_stage_us:stages,
    level_low_v:levels,level_mid_v:levels,level_high_v:levels};
  for(const key of extraKeys)card.querySelector(`[data-param="${key}"]`).closest(".field").hidden=!visible[key];
  const countInput=card.querySelector('[data-param="pulse_count"]'),countLabel=vin?"Vin 脉冲数量":"Vgate 脉冲数量";
  countInput.setAttribute("aria-label",countLabel);countInput.closest(".field").querySelector("label").textContent=countLabel;
  card.querySelector(".simple-params").hidden=!firing&&mode!==24;
  const hint=card.querySelector(".simple-hint");hint.hidden=!firing&&mode!==24;
  hint.textContent=mode===12&&!vin?"Vgate 为恒压，只需设置上方幅值；Vin 的脉宽和间隔不会改变 Gate。":
    "脉宽、间隔填写实际 μs，互不挤占；留空沿用原模板。";
  if([11,12].includes(mode))hint.textContent=vin?
    "这里设置单个方波的周期时长和占空比：脉宽 = 周期时长 × 占空比，间隔 = 周期时长 − 脉宽；上方时长是整组时窗。留空沿用当前变体。":
    mode===11?"Vgate 用频率设置正弦，峰值对齐 Vin 第一个方波中心；当正弦周期与方波周期相等时每个脉冲均对齐。正弦周期 / μs = 1000 ÷ 频率 / kHz。":"Vgate 为恒压，只需设置上方电压。";
  if(stages)hint.textContent=mode===7?"第一段从 0 V 斜坡升至第一段电压，再以第二段电压保持；两段时间分别填写实际 μs。":
    topology===7?"第一段方波接第二段方波；两段电压和时间分别设置，时间填写实际 μs。":
    "第一段从第一段电压斜坡变化至第二段电压，第二段保持；两段时间分别填写实际 μs。";
  if(mode===6&&!vin)hint.textContent="Vgate 从开始电压斜坡变化至结束电压；脉宽设置斜坡持续时间（实际 μs）。";
  if(levels)hint.textContent+=" 三档电压分别填写，数值不再乘以幅值；通道偏移仍会叠加。";
  if(mode===12&&vin)hint.textContent+=" 快、慢脉冲通过实验变体分别测试，每次只输出一组。";
  if(firing){
    if([10,11].includes(mode))card.querySelector('[data-param="gate_sine_period_us"]').closest(".field").hidden=true;
    for(const key of ["rise_us","fall_us"])card.querySelector(`[data-param="${key}"]`).closest(".field").hidden=true;
    card.querySelector('[data-param="width_us"]').closest(".field").hidden=true;
    if([11,12].includes(mode))card.querySelector('[data-param="pulse_period_us"]').closest(".field").hidden=true;
    if(mode===22)card.querySelector('[data-param="gap_us"]').closest(".field").hidden=true;
    if([15,21].includes(mode))card.querySelector('[data-param="levels_v"]').closest(".field").hidden=true;
    if([11,12].includes(mode))for(const key of ["width_us","gap_us","pulse_period_us","gate_sine_period_us"])
      card.querySelector(`[data-param="${key}"]`).closest(".field").hidden=true;
    if([5,6,7].includes(mode))card.querySelector('[data-param="ramp_us"]').closest(".field").hidden=true;
  }
  const voltageKeys=levels?["level_low_v","level_mid_v","level_high_v"]:stages?["stage1_voltage_v","stage2_voltage_v"]:mode===6&&!vin?["gate_initial_v","gate_final_v"]:[];
  const explicitLevels=voltageKeys.some(k=>card.querySelector(`[data-param="${k}"]`).value.trim());
  field("amplitude").disabled=explicitLevels;
  card.querySelector('[data-action="peak"]').disabled=explicitLevels;
  const dc=constantCard(card);
  card.dataset.outputKind=dc?"constant":"dynamic";
  field("duration").closest(".field").hidden=dc||mode===24;
  field("timeShift").closest(".field").hidden=dc||mode===24;
  field("component").closest(".field").hidden=dc||mode===12||mode>=24;
  card.querySelector(".advanced").hidden=dc||mode===24||mode===26||(mode===11&&!vin);
  if(mode===24)hint.textContent=vin?"2000 μs = 2 ms。每次点击只输出一次，时间到后自动归零；无需设置整组时窗。":
    "提前/延后时间相对配对 Vin 设置。长脉冲相邻切换至少间隔 300 μs；更短组合会检查能否用 SRAM 完成。";
  if(hasEdges)hint.textContent+=" 上升、下降时间为实际 0～1 μs；0 表示数字跳变，留空保留模板。";
  if(mode===24)hint.textContent+=" 非零边沿使用 SRAM，完整包络超容量时需缩短脉宽或提前/延后时间。";
  if(dc){
    field("amplitude").closest(".field").querySelector("label").textContent=`${vin?"Vin":"Vgate"} 恒定电压 / V`;
    field("amplitude").disabled=false;
    card.querySelector(".simple-params").hidden=true;
    hint.hidden=false;
    hint.textContent=`${vin?"Vin":"Vgate"} 全程恒压，只设置电压和电压偏移；无周期、脉宽或时间偏移，SRAM 占用 0 点。全部 4096 点可供已启用的动态通道使用。`;
  }
  if(rhythmMode(mode)){
    const square=vin||mode===28;
    const rhythmFields={rhythm_on_us:vin,rhythm_frequency_khz:!vin,rhythm_duty_percent:square,rhythm_phase_deg:true,
      rise_time_us:square,fall_time_us:square};
    const defaults={rhythm_on_us:20,rhythm_frequency_khz:25,rhythm_duty_percent:50,rhythm_phase_deg:0,rise_time_us:0,fall_time_us:0};
    for(const input of card.querySelectorAll('[data-param]')){
      const key=input.dataset.param;input.closest('.field').hidden=!rhythmFields[key];
      if(rhythmFields[key]&&input.value==='')input.value=defaults[key];
    }
    card.querySelector('.simple-params').hidden=false;hint.hidden=false;
    card.querySelector('.advanced').hidden=true;
    for(const name of ['variant','component','timeShift'])field(name).closest('.field').hidden=true;
    field('duration').closest('.field').hidden=false;
    field('duration').closest('.field').querySelector('label').textContent='单次观察时长 / μs';
    field('amplitude').closest('.field').querySelector('label').textContent='幅值 / V（中心到峰值）';
    card.querySelector('[data-action="peak"]').hidden=true;
    hint.textContent=vin?'默认 ON 20 μs、占空比 50%，对应 25 kHz；观察窗与配对通道联动。':'本路频率和初始相位独立设置；频率不同时，相位差随时间变化。';
    hint.textContent+=' 相位 0° 对应方波上升沿或正弦向上过中心电压，正值提前；单次输出后归零。';
    if(square)hint.textContent+=' 上升、下降时间可分别设为 0～1 μs，计入 ON 时间；0 为数字跳变，两者之和不能超过 ON 时间。';
  }
}

function pairedPeer(card,mode=card.querySelector('[data-field="mode"]').value){
  const field=(node,name)=>node.querySelector(`[data-field="${name}"]`);
  const pair=field(card,"pair").value;
  if(!pair||!field(card,"enabled").checked)return null;
  const members=[...document.querySelectorAll(".channel-card")].filter(node=>
    field(node,"enabled").checked&&field(node,"pair").value===pair);
  if(members.length!==2)return null;
  const peer=members.find(node=>node!==card);
  if(field(peer,"signal").value===field(card,"signal").value||
    field(peer,"topology").value!==field(card,"topology").value||field(peer,"mode").value!==mode)return null;
  return peer;
}

function updatePairStatus(){
  for(const card of document.querySelectorAll(".channel-card")){
    const peer=pairedPeer(card),note=card.querySelector(".pair-note");
    note.textContent=peer?(rhythmMode(card.querySelector('[data-field="mode"]').value)?`节律配对 DAC${peer.dataset.channel} · 频率、初始相位独立`:`已配对 DAC${peer.dataset.channel} · 模式自动联动`):"当前未配对";
    note.classList.toggle("unpaired",!peer);
  }
}

function resetMode(card){
  for(const input of card.querySelectorAll("[data-param]"))input.value="";
  updateVariantChoices(card,0,null);
  if(Number(card.querySelector('[data-field="mode"]').value)>=25){
    card.querySelector('[data-field="duration"]').value=rhythmMode(card.querySelector('[data-field="mode"]').value)?200:Number(card.querySelector('[data-field="mode"]').value)===26?1:1000;
    card.querySelector('[data-field="timeShift"]').value=0;
  }
  card.querySelector('[data-field="amplitude"]').value=peakFor(card);
  card.dataset.previousMode=card.querySelector('[data-field="mode"]').value;
}

function syncPairedWindow(card,input){
  if(!["duration","mode","variant","pair","enabled"].includes(input.dataset.field))return;
  const peer=pairedPeer(card);
  if(!peer||constantCard(card)||constantCard(peer))return;
  peer.querySelector('[data-field="duration"]').value=card.querySelector('[data-field="duration"]').value;
}

function upgradeLegacyRhythm(scene){
  if(!scene.rhythm_modulation)return scene;
  const result=JSON.parse(JSON.stringify(scene)),active=result.channels.filter(b=>b.enabled!==false);
  const gate=active.find(b=>b.signal==='gate');
  if(active.length!==2||!gate||!active.every(b=>[25,26].includes(Number(b.mode))))return scene;
  const mode=Number(gate.mode)===26?27:28,window=result.rhythm_modulation.duration_us??200;
  for(const b of active){
    const frequency=b.frequency_hz??1e6/b.duration_us,duty=b.parameters?.duty_percent??50;
    const phase=b.phase_deg??-(b.time_offset_us??0)*frequency*360/1e6;
    b.parameters={rhythm_phase_deg:phase};
    if(b.signal==='vin')Object.assign(b.parameters,{rhythm_on_us:1e6/frequency*duty/100,rhythm_duty_percent:duty});
    else {b.parameters.rhythm_frequency_khz=frequency/1000;if(mode===28)b.parameters.rhythm_duty_percent=duty;}
    Object.assign(b,{mode,duration_us:window,variant:0,component:'rhythm'});
    delete b.frequency_hz;delete b.phase_deg;delete b.time_offset_us;
  }
  delete result.rhythm_modulation;
  return result;
}

function startRhythmMode(card){
  const field=(node,key)=>node.querySelector(`[data-field="${key}"]`),mode=Number(field(card,'mode').value);
  const previous=card.dataset.previousMode,number=Number(card.dataset.channel),sourceVin=field(card,'signal').value==='vin';
  const peer=pairedPeer(card,previous)||document.querySelector(`.channel-card[data-channel="${number%2?number+1:number-1}"]`);
  const pair=field(card,'pair').value||(number<=2?'A':'B'),topology=field(card,'topology').value;
  const duration=rhythmMode(previous)?field(card,'duration').value:200;
  for(const node of document.querySelectorAll('.channel-card')){
    const active=node===card||node===peer;
    if(active){
      const keep=rhythmMode(node.dataset.previousMode),old={};
      for(const key of ['rhythm_on_us','rhythm_frequency_khz','rhythm_duty_percent','rhythm_phase_deg','rise_time_us','fall_time_us'])old[key]=node.querySelector(`[data-param="${key}"]`).value;
      const amplitude=keep?field(node,'amplitude').value:.5,offset=keep?field(node,'offset').value:.5;
      field(node,'mode').value=mode;field(node,'signal').value=(node===card?sourceVin:!sourceVin)?'vin':'gate';
      field(node,'pair').value=pair;field(node,'topology').value=topology;
      resetMode(node);field(node,'duration').value=duration;field(node,'amplitude').value=amplitude;field(node,'offset').value=offset;
      if(keep)for(const [key,value] of Object.entries(old))if(value!=='')node.querySelector(`[data-param="${key}"]`).value=value;
    }
    field(node,'enabled').checked=active;node.classList.toggle('disabled',!active);updateSimpleControls(node);
  }
  updatePairStatus();schedulePreview();
  log(`已启用模式 ${mode} 的 Vin / Vgate 配对，其他通道已关闭；修改参数后会自动更新预览。`,'success');
}

function applyScene(scene){
  if(!scene||!Array.isArray(scene.channels))throw new Error("场景 JSON 缺少 channels 数组");
  scene=upgradeLegacyRhythm(scene);
  state.scene=scene;
  el("intervalSeconds").value=scene.interval_s??1;
  el("repeatCount").value=scene.repeat_count??1;
  const host=el("channelEditors");host.replaceChildren();
  for(let n=1;n<=4;n++){
    const binding=scene.channels.find(c=>Number(c.channel)===n)||{channel:n,enabled:false},card=createEditor(n,binding);
    host.append(card);
  }
  updatePairStatus();
  schedulePreview();
}

function number(value,label){
  if(String(value).trim()==="")throw new Error(`${label}不能为空`);
  const parsed=Number(value);
  if(!Number.isFinite(parsed))throw new Error(`${label}须填写有效数字`);
  return parsed;
}

function collectScene(){
  const scene={...(state.scene||{})};
  scene.interval_s=number(el("intervalSeconds").value,"波形间隔");
  scene.repeat_count=number(el("repeatCount").value,"触发组数");
  if(!Number.isInteger(scene.repeat_count)||scene.repeat_count<1||scene.repeat_count>1000)throw new Error("触发组数须为 1～1000 的整数");
  if(scene.interval_s<0.01||scene.interval_s>3600)throw new Error("波形间隔须为 0.01～3600 秒");
  scene.channels=[...document.querySelectorAll(".channel-card")].map(card=>{
    const f=name=>card.querySelector(`[data-field="${name}"]`);
    const n=Number(card.dataset.channel),params={},dc=constantCard(card);
    for(const input of card.querySelectorAll("[data-param]")){
      if(dc)continue;
      const text=input.value.trim(),key=input.dataset.param;
      const mode=Number(f("mode").value);
      if(rhythmMode(mode)){
        const vin=f('signal').value==='vin',edge=['rise_time_us','fall_time_us'].includes(key)&&(vin||mode===28);
        if(!edge&&!(key==='rhythm_phase_deg'||(vin?['rhythm_on_us','rhythm_duty_percent'].includes(key):key==='rhythm_frequency_khz'||(mode===28&&key==='rhythm_duty_percent'))))continue;
      }
      if(!rhythmMode(mode)&&key.startsWith('rhythm_'))continue;
      if(mode===24&&!["rise_time_us","fall_time_us",...(f("signal").value==="vin"?["width_us"]:["gate_lead_us","gate_tail_us"])].includes(key))continue;
      if((mode===25&&key!=="duty_percent")||mode===26||(mode<25&&key==="duty_percent"))continue;
      if(!text)continue;
      if(key==="levels_v"){
        const bits=text.split(",").map(p=>p.trim());
        if(bits.length!==3)throw new Error(`DAC${n} 三档电压需要三个数`);
        params[key]=bits.map(p=>number(p,`DAC${n} 三档电压`));
      }else{
        params[key]=number(text,`DAC${n} ${paramLabels[key]}`);
        if((key==="rise_time_us"||key==="fall_time_us")&&(params[key]<0||params[key]>1))
          throw new Error(`DAC${n} 上升时间和下降时间须在 0～1 μs 范围内`);
        if(key==="pulse_count"&&!Number.isInteger(params[key]))throw new Error(`DAC${n} 脉冲列数量应为整数`);
      }
    }
    if(params.vin_period_us!==undefined||params.pulse_gap_us!==undefined)delete params.pulse_period_us;
    if(params.pulse_gap_us!==undefined)delete params.gap_us;
    if(params.vin_duty_percent!==undefined){delete params.vin_width_us;delete params.width_us;delete params.pulse_gap_us}
    if(params.gate_frequency_khz!==undefined)delete params.gate_sine_period_us;
    if(params.first_stage_us!==undefined||params.second_stage_us!==undefined){delete params.ramp_us;delete params.width_us}
    if(Number(f("mode").value)===6&&params.gate_width_us!==undefined)delete params.ramp_us;
    const channel={channel:n,enabled:f("enabled").checked,topology:Number(f("topology").value),
      mode:Number(f("mode").value),signal:f("signal").value,variant:Number(f("variant").value),
      component:f("component").value,
      amplitude_v:number(f("amplitude").value,`DAC${n} 幅值`),offset_v:number(f("offset").value,`DAC${n} 偏移`),
      time_offset_us:dc||rhythmMode(f('mode').value)?0:number(f("timeShift").value,`DAC${n} 时间偏移`)};
    if(channel.mode===24){delete channel.time_offset_us;}
    else if(rhythmMode(channel.mode)){delete channel.time_offset_us;channel.duration_us=number(f('duration').value,`DAC${n} 观察时长`);}
    else if(!dc&&channel.mode===26){
      channel.frequency_hz=number(f("duration").value,`DAC${n} 正弦频率`)*1000;
      if(channel.frequency_hz<=0)throw new Error(`DAC${n} 正弦频率必须大于 0`);
    }else if(!dc)channel.duration_us=number(f("duration").value,`DAC${n} 时窗 / 单周期时长`);
    else delete channel.time_offset_us;
    if(!dc&&channel.duration_us<=0)throw new Error(`DAC${n} 时窗 / 单周期时长必须大于 0`);
    if(f("pair").value)channel.pair=f("pair").value;
    if(Object.keys(params).length)channel.parameters=params;
    return channel;
  });
  scene.static_pulse=scene.channels.some(b=>b.enabled&&b.mode===24);
  delete scene.rhythm_modulation;
  if(scene.static_pulse){scene.repeat_count=1;el("repeatCount").value=1;}
  return scene;
}

function schedulePreview(){
  clearTimeout(state.previewTimer);state.previewToken++;state.preview=null;updateControls();
  el("previewFlag").textContent="正在编译";el("previewFlag").className="pill waiting";
  state.previewTimer=setTimeout(previewScene,320);
}

async function previewScene(){
  const token=++state.previewToken;
  let scene;
  try{scene=collectScene()}catch(error){showPreviewError(error.message);return}
  try{
    const result=await api("/api/preview",{scene});
    if(token!==state.previewToken)return;
    state.preview=result;
    renderPreview(result);
  }catch(error){if(token===state.previewToken)showPreviewError(error.message)}
  updateControls();
}

function showPreviewError(message){
  state.preview=null;el("previewFlag").textContent="不可发送";el("previewFlag").className="pill bad";
  el("previewError").hidden=false;el("previewError").textContent=message;
  for(const id of ["frameDuration","memoryUsed","timingValue"])el(id).textContent="—";
  el("resourceNotes").textContent="";
  updateControls();
}

function formatDuration(value){
  if(value===null||value===undefined||!Number.isFinite(value))return "—";
  return `${Number(value.toPrecision(8)).toLocaleString("zh-CN",{maximumSignificantDigits:8})} μs`;
}

function formatFrequency(value){
  if(!Number.isFinite(value)||value<=0)return "—";
  return `${Number((value>=1000?value/1000:value).toPrecision(8)).toLocaleString("zh-CN",{maximumSignificantDigits:8})} ${value>=1000?"kHz":"Hz"}`;
}

function renderPreview(result){
  const warnings=result.channels.flatMap(row=>(row.sampling_warnings||[]).map(note=>`DAC${row.channel}：${note}`));
  const quantized=result.channels.filter(row=>row.snapped);
  const hasWarnings=warnings.length||quantized.length;
  el("previewFlag").textContent=result.ok?(hasWarnings?"可发送 · 请检查细节":"可发送"):"需要调整";
  el("previewFlag").className=`pill ${result.ok?(hasWarnings?"waiting":"good"):"bad"}`;
  el("previewError").hidden=result.ok;
  el("previewError").textContent=result.ok?"":`当前配置无法一起发送：${result.error}。下图仅用于检查单路形状，修正后会重新编译。`;
  el("frameDuration").textContent=result.ok?formatDuration(result.summary.frame_duration_us):"—";
  el("memoryUsed").textContent=result.ok?`${result.summary.sram_words} / 4096 点`:"—";
  const sramRow=result.channels.find(row=>row.source==="sram");
  const sampleInterval=result.summary?.sample_interval_us??sramRow?.step_us??null;
  const freeWords=result.ok?(result.summary.sram_free_words??(4096-result.summary.sram_words)):null;
  el("timingValue").textContent=result.ok?(sampleInterval===null?"不使用 SRAM":formatDuration(sampleInterval)):"—";
  el("resourceNotes").textContent=result.ok?
    `剩余 ${freeWords} 点。${sampleInterval===null?"":`HOLD=${result.summary.hold}；`}最大整组时长误差 ${formatDuration(result.summary.max_duration_error_us)}。`+
    (warnings.length?` ${warnings.join("；")}。`:"")+
    (quantized.length?` ${quantized.map(row=>`DAC${row.channel}`).join("、")}存在窄平台量化，请检查波形。`:""):
    "未找到可发送的联合方案；以下为理论形状，不代表已通过存储和采样精度检查。";
  const rhythm=result.summary?.rhythm_modulation;
  el("previewTitle").textContent=rhythm?"节律输出波形预览":"四路输出波形预览";
  el("previewCaption").textContent=rhythm?
    "图为观察窗内实际编译的两路激励采样，结束时回到数字零码。两路共用 4096 点 SRAM；窗内不重置相位，各次触发重新从初始相位开始。纵轴为名义电压，发放波形由示波器测量。":
    "波形依据已编译的 DAC 码绘制，纵轴为名义电压；图文模板中未明确的时序为近似值。支持保留细节的波形可将时窗扩展至 1000 μs，末尾零码等待由芯片计时。超出能力时拒绝发送，不自动更改其他通道。编译失败时显示单路模板预览。";
  if(result.ok&&rhythm)el("resourceNotes").textContent+=` 节律观察 ${formatDuration(rhythm.observation_duration_us)}；Δf=${Number(rhythm.frequency_difference_hz.toPrecision(8))} Hz；初始相位差 ${Number(rhythm.initial_phase_difference_deg.toPrecision(8))}°，窗内漂移 ${Number(rhythm.phase_drift_deg.toPrecision(8))}°。末尾附一个零码采样，单次播放，不在窗内重置相位。`;
  const host=el("charts");host.replaceChildren();
  for(const row of result.channels){
    if(rhythm&&!row.signal)continue;
    const card=document.createElement("article");card.className="chart-card";
    const head=document.createElement("div");head.className="chart-head";
    const title=document.createElement("strong");title.textContent=`DAC${row.channel} · ${row.signal==="gate"?"Vgate":row.signal==="vin"?"Vin":"未启用"}`;
    const timing=document.createElement("small");timing.textContent=rhythm&&row.frequency_hz?`${row.waveform==='sine'||row.mode===26?"正弦":"方波"} ${formatFrequency(row.frequency_hz)}`:row.pulse_width_us?`单次保持 ${formatDuration(row.pulse_width_us)}`:row.source==="constant"?"直流":row.mode===26?`正弦 ${formatFrequency(row.frequency_hz)}`:row.period_us?`${row.mode>=25?"单周期":"整组时窗"} ${formatDuration(row.period_us)}`:"—";
    head.append(title,timing);
    const canvas=document.createElement("canvas");canvas.setAttribute("aria-label",`DAC${row.channel} 波形图`);
    const meta=document.createElement("div");meta.className="chart-meta";
    meta.textContent=row.error?row.error:row.source==="template"?"理论波形 · 当前配置不可发送（原因见上方）":
      row.source==="constant"?`直流 · ${Number(row.min_v).toFixed(3)} V* · SRAM 0 点，容量留给动态通道`:
      row.source==="disabled"?"零码 / 通道未启用":
      `T${row.topology} / ${String(row.mode).padStart(2,"0")} · ${row.min_v.toFixed(3)}…${row.max_v.toFixed(3)} V*${row.snapped?` · 窄平台量化 ${row.snapped} 点`:""}`;
    if(row.source==="sram"){
      const shared=Array.isArray(row.shared_with)?row.shared_with:null;
      meta.textContent+=` · SRAM ${row.sram_words??row.samples?.length??"—"} 点`+
        (shared===null?"（服务未提供共享信息）":shared.length?`（与 ${shared.map(n=>`DAC${n}`).join("、")}共用）`:"（独占）");
    }
    if(row.zero_tail_samples)meta.textContent+=` · 末尾 ${row.zero_tail_us.toFixed(2)} us 零码等待由芯片计时`;
    if(row.carrier_hz||row.carrier_period_us)meta.textContent+=` · 正弦频率 ${formatFrequency(row.carrier_hz||(1e6/row.carrier_period_us))}`;
    if(row.source==="dds")meta.textContent+=" · DDS 实际频率 · 曲线为解析预览";
    if(row.source==="fpga_square")meta.textContent+=" · FPGA 定时切换电平";
    if(row.source==="fpga_pulse")meta.textContent+=" · FPGA 定时单脉冲 · SRAM 0 点 · 结束归零";
    if(rhythm&&row.initial_phase_deg!==null&&row.initial_phase_deg!==undefined)meta.textContent+=` · 初始相位 ${Number((((row.initial_phase_deg+180)%360+360)%360-180).toPrecision(8))}°`;
    else if(row.time_offset_us)meta.textContent+=` · 时间偏移 ${formatDuration(row.time_offset_us)}`;
    if(rhythm&&row.max_phase_quantization_deg)meta.textContent+=` · 每采样约 ${row.max_phase_quantization_deg.toFixed(3)}°`;
    if(rhythm&&row.rise_time_us!==null&&row.rise_time_us!==undefined)meta.textContent+=` · 上升/下降 ${row.rise_time_us}/${row.fall_time_us} μs`;
    card.append(head,canvas,meta);host.append(card);
    requestAnimationFrame(()=>drawChart(canvas,row));
  }
}

function drawChart(canvas,row){
  const rect=canvas.getBoundingClientRect(),width=Math.max(240,rect.width),height=Math.max(160,rect.height);
  const dpr=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
  const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,width,height);
  const margin={l:43,r:13,t:11,b:27},w=width-margin.l-margin.r,h=height-margin.t-margin.b;
  const raw=row.samples||[],values=raw.map(v=>row.source==="template"?v:
    (row.zero_code_v||0)+v*(row.full_scale_v||10)/2048);
  if(!values.length){ctx.fillStyle="#8b9daf";ctx.font="12px sans-serif";ctx.fillText("参数无效",margin.l,75);return}
  let min=Math.min(...values),max=Math.max(...values);
  const pad=Math.max(.35,(max-min)*.13);min-=pad;max+=pad;
  const y=v=>margin.t+h-(v-min)/(max-min)*h;
  ctx.font="10px sans-serif";ctx.fillStyle="#71829a";ctx.strokeStyle="#e6edf3";ctx.lineWidth=1;
  for(let k=0;k<4;k++){
    const lineY=margin.t+k*h/3;
    ctx.beginPath();ctx.moveTo(margin.l,lineY);ctx.lineTo(margin.l+w,lineY);ctx.stroke();
    const value=max-k*(max-min)/3;
    ctx.fillText(value.toFixed(1),4,lineY+3);
  }
  ctx.beginPath();ctx.moveTo(margin.l,margin.t);ctx.lineTo(margin.l,margin.t+h);ctx.lineTo(margin.l+w,margin.t+h);ctx.strokeStyle="#b8c8d8";ctx.stroke();
  ctx.fillStyle="#71829a";ctx.fillText("0",margin.l,margin.t+h+16);
  ctx.fillText(`${Number(row.duration_us||0).toFixed(2)} us`,margin.l+w-49,margin.t+h+16);
  const buckets=new Array(Math.max(1,Math.round(w)));
  const total=row.total_samples||values.length;
  for(let i=0;i<values.length;i++){
    const x=Math.min(buckets.length-1,Math.floor(i/total*buckets.length));
    if(!buckets[x])buckets[x]=[values[i],values[i]];
    else{buckets[x][0]=Math.min(buckets[x][0],values[i]);buckets[x][1]=Math.max(buckets[x][1],values[i])}
  }
  if(row.zero_tail_samples){
    const idle=row.zero_code_v||0;
    for(let x=Math.floor(values.length/total*buckets.length);x<buckets.length;x++){
      if(!buckets[x])buckets[x]=[idle,idle];
      else{buckets[x][0]=Math.min(buckets[x][0],idle);buckets[x][1]=Math.max(buckets[x][1],idle)}
    }
  }
  const color=row.signal==="gate"?"#c87921":row.source==="disabled"?"#9aabba":"#1767a2";
  if(Array.isArray(row.sample_times_us)&&row.sample_times_us.length===values.length){
    ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();
    row.sample_times_us.forEach((t,i)=>{const x=margin.l+w*t/row.duration_us;if(i)ctx.lineTo(x,y(values[i]));else ctx.moveTo(x,y(values[i]));});
    ctx.stroke();return;
  }
  ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();
  let last=null;
  for(let i=0;i<buckets.length;i++){
    const pair=buckets[i];if(!pair)continue;
    const x=margin.l+i+.5,center=(pair[0]+pair[1])/2;
    if(last)ctx.moveTo(last[0],y(last[1])),ctx.lineTo(x,y(center));
    ctx.moveTo(x,y(pair[0]));ctx.lineTo(x,y(pair[1]));
    last=[x,center];
  }
  if(values.length===1){ctx.moveTo(margin.l,y(values[0]));ctx.lineTo(margin.l+w,y(values[0]))}
  ctx.stroke();
}

function setConnected(port){
  state.connectedPort=port;
  const box=el("portState");box.className=`port-state ${port?"connected":"disconnected"}`;
  box.lastElementChild.textContent=port?`已检测 ${port}`:"未连接";
  updateControls();
}

function updateControls(){
  const port=el("portSelect").value,connected=port&&port===state.connectedPort;
  el("probePort").disabled=state.busy||!port;
  el("readRegisters").disabled=state.busy||!connected;
  el("sendScene").disabled=state.busy||!connected||!state.preview?.ok;
  el("abortOutput").disabled=!connected;
  el("refreshPorts").disabled=state.busy;
  const staticPulse=[...document.querySelectorAll('.channel-card')].some(card=>card.querySelector('[data-field="enabled"]').checked&&card.querySelector('[data-field="mode"]').value==='24');
  el("intervalSeconds").disabled=state.busy||staticPulse;
  el("repeatCount").disabled=state.busy||staticPulse;
  if(staticPulse)el("repeatCount").value=1;
  el("playbackHint").textContent=rhythmActive()?"节律实验：每次触发播放一个观察窗后归零；组数大于 1 时，各组重新从所设初始相位开始。":staticPulse?"静态扫描：每次点击只输出一次。Vgate 提前建立并延后归零；Vin 保持指定时长后归零。长脉冲使用已有 FPGA 定时事件固件。":
    "普通波形每次触发连续播放两遍预览单元；组间等待设定时间。组数为 1 时只触发一次。";
  document.body.classList.toggle("busy",state.busy);
  for(const id of ["importScene","saveScene","downloadScene","syncPairs"])el(id).disabled=state.busy;
}

async function refreshPorts(){
  if(state.busy)return;
  try{
    const result=await api("/api/ports"),select=el("portSelect"),old=select.value;
    select.replaceChildren();
    if(!result.ports.length)option(select,"","未发现串口");
    else for(const port of result.ports)option(select,port.device,`${port.device} · ${port.description}`);
    choose(select,old);
    if(select.value!==state.connectedPort)setConnected(null);
    el("serialHint").textContent=result.pyserial_available?"串口列表会自动刷新；切换串口后请重新检测设备。":
      "当前 Python 未安装 pyserial；可以配置和预览波形。要检测或发送，请在终端执行：python -m pip install pyserial";
    updateControls();
  }catch(error){log(`串口扫描失败：${error.message}`,"error")}
}

async function probe(){
  const port=el("portSelect").value;if(!port)return;
  state.busy=true;updateControls();
  try{
    const result=await api("/api/probe",{port});
    setConnected(port);log(result.message,"success");
  }catch(error){setConnected(null);log(`设备检测失败：${error.message}`,"error")}
  finally{state.busy=false;updateControls()}
}

async function save(){
  try{const scene=collectScene(),result=await api("/api/save",{scene});state.scene=scene;log(result.message,"success")}
  catch(error){log(`保存失败：${error.message}`,"error")}
}

function download(){
  try{
    const scene=collectScene(),blob=new Blob([JSON.stringify(scene,null,2)],{type:"application/json"});
    const link=document.createElement("a");link.href=URL.createObjectURL(blob);
    link.download="ad9106_firing_scene.json";link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    log("已下载四路场景 JSON。","success");
  }catch(error){log(`下载失败：${error.message}`,"error")}
}

function syncPairs(){
  try{
    const scene=collectScene();
    for(const [a,b,label] of [[0,1,"A"],[2,3,"B"]]){
      const source=scene.channels[a],target=scene.channels[b];
      const changed=target.topology!==source.topology||target.mode!==source.mode||target.signal===source.signal;
      for(const key of ["topology","mode","variant","component"]){
        if(source[key]===undefined)delete target[key];else target[key]=JSON.parse(JSON.stringify(source[key]));
      }
      target.enabled=source.enabled;target.signal=source.signal==="vin"?"gate":"vin";
      source.pair=label;target.pair=label;
      const e=entry(target.topology,target.mode),c=e.cases.find(x=>x.variant===target.variant);
      if(changed){
        target.parameters={};target.time_offset_us=0;target.offset_v=0;
        delete target.frequency_hz;
        target.amplitude_v=Math.min(10,Math.max(...c[`${target.signal}_range_v`].map(Math.abs)));
      }
      if(!constantBinding(source)&&!constantBinding(target)){
        if(source.mode===26){target.frequency_hz=source.frequency_hz;delete target.duration_us;}
        else target.duration_us=source.duration_us;
      }
    }
    applyScene(scene);log("两组配对的拓扑、模式、实验和分段已同步；两路均为动态输出时同步时窗，各路电压、边沿和时间偏移保留。","success");
  }catch(error){log(`配对失败：${error.message}`,"error")}
}

function configureStaticPair34(){
  const scene={...(state.scene||{})};
  delete scene.rhythm_modulation;
  scene.static_pulse=true;scene.repeat_count=1;
  const old=Array.isArray(scene.channels)?scene.channels:[];
  scene.channels=[1,2].map(n=>({...old.find(c=>Number(c.channel)===n),channel:n,enabled:false}));
  for(const [channel,signal,amplitude] of [[3,"vin",1],[4,"gate",0]]){
    scene.channels.push({channel,enabled:true,topology:6,mode:24,signal,
      variant:0,component:"pulse",duration_us:100,amplitude_v:amplitude,
      offset_v:0,time_offset_us:0,pair:"B",
      parameters:signal==="vin"?{width_us:2000}:{gate_lead_us:300,gate_tail_us:300}});
  }
  scene.interval_s=1;scene.repeat_count=1;
  applyScene(scene);
  log("已设 DAC3=Vin 单脉冲、DAC4=Vgate 有限包络。请设置两路电压、Vin 脉宽以及 Vgate 提前/延后时间。","success");
}

async function send(){
  if(state.busy)return;
  let scene;
  try{scene=collectScene()}catch(error){log(`配置有误：${error.message}`,"error");return}
  state.busy=true;updateControls();
  try{
    const result=await api("/api/send",{port:el("portSelect").value,scene});
    state.scene=scene;state.jobId=result.id;
    el("uploadProgress").max=result.total;el("uploadProgress").value=0;
    el("progressText").textContent=`0 / ${result.total} 帧`;
    log(`开始发送 ${result.total} 帧；四路在最终提交后一起启动。`);
    pollJob();
  }catch(error){state.busy=false;updateControls();log(`发送失败：${error.message}`,"error")}
}

async function pollJob(){
  const id=state.jobId;if(!id)return;
  try{
    const job=await api(`/api/job?id=${encodeURIComponent(id)}`);
    el("uploadProgress").max=job.total;el("uploadProgress").value=job.done;
    el("progressText").textContent=`${job.done} / ${job.total} 帧`;
    if(job.status==="running"){
      el("progressText").textContent=`${job.done} / ${job.total} 帧 · ${job.message}`;
      setTimeout(pollJob,400);return
    }
    state.busy=false;state.jobId=null;
    if(job.status==="complete"||job.status==="cancelled")log(job.message,"success");
    else{setConnected(null);log(`上传失败：${job.message}。请刷新串口并重新检测。`,"error")}
    updateControls();
  }catch(error){setTimeout(pollJob,1000);log(`读取上传进度失败：${error.message}`,"error")}
}

async function abort(){
  const port=el("portSelect").value;if(!port)return;
  if(state.busy){
    try{const result=await api("/api/abort",{port});log(result.message,"success")}
    catch(error){log(`停止失败：${error.message}`,"error")}
    return;
  }
  state.busy=true;updateControls();
  try{const result=await api("/api/abort",{port});log(result.message,"success")}
  catch(error){log(`停止失败：${error.message}`,"error")}
  finally{state.busy=false;updateControls()}
}

el("channelEditors").addEventListener("change",event=>{
  const card=event.target.closest(".channel-card");if(!card)return;
  const field=event.target.dataset.field;
  if(field==='mode'&&rhythmMode(event.target.value)){startRhythmMode(card);return;}
  if(field==="topology"||field==="mode"){
    const peer=field==="mode"?pairedPeer(card,card.dataset.previousMode):null;
    resetMode(card);
    if(field==="mode"){
      if(peer){
        peer.querySelector('[data-field="mode"]').value=event.target.value;
        resetMode(peer);
        log(`DAC${card.dataset.channel} / DAC${peer.dataset.channel} 已同步切换到模式 ${event.target.value}。`,"success");
      }else log(`DAC${card.dataset.channel} 当前未配对，仅修改本通道模式。`,"error");
    }
  }else if(field==="variant"||field==="component"){
    const peer=pairedPeer(card),variant=Number(card.querySelector('[data-field="variant"]').value);
    const component=card.querySelector('[data-field="component"]').value;
    for(const target of peer?[card,peer]:[card]){
      if(field==="variant"&&[11,12].includes(Number(card.querySelector('[data-field="mode"]').value)))
        for(const key of ["vin_period_us","vin_duty_percent","vin_width_us","pulse_gap_us","pulse_period_us","width_us"])
          target.querySelector(`[data-param="${key}"]`).value="";
      updateVariantChoices(target,variant,component);
      target.querySelector('[data-field="amplitude"]').value=peakFor(target);
    }
    if(!peer)log(`DAC${card.dataset.channel} 当前未配对，仅修改本通道${field==="variant"?"实验变体":"分段"}。`,"error");
  }else if(field==="signal"){
    if(field==="signal")updateVariantChoices(card,Number(card.querySelector('[data-field="variant"]').value),card.querySelector('[data-field="component"]').value);
    card.querySelector('[data-field="amplitude"]').value=peakFor(card);
  }
  if(field==="enabled")card.classList.toggle("disabled",!event.target.checked);
  updateSimpleControls(card);syncPairedWindow(card,event.target);
  updatePairStatus();
  schedulePreview();
});
el("channelEditors").addEventListener("input",event=>{
  const card=event.target.closest(".channel-card");
  if(card){updateSimpleControls(card);syncPairedWindow(card,event.target)}
  schedulePreview();
});
el("channelEditors").addEventListener("click",event=>{
  if(event.target.dataset.action==="peak"){
    const card=event.target.closest(".channel-card");
    card.querySelector('[data-field="amplitude"]').value=peakFor(card);schedulePreview();
  }
});
el("refreshPorts").addEventListener("click",refreshPorts);
el("portSelect").addEventListener("change",()=>setConnected(null));
el("probePort").addEventListener("click",probe);
el("readRegisters").addEventListener("click",async()=>{
  if(state.busy)return;
  state.busy=true;updateControls();
  try{
    const result=await api("/api/registers",{port:el("portSelect").value});
    const values=Object.entries(result.registers).map(([a,v])=>`${a}=0x${v.toString(16).padStart(4,"0")}`).join(" · ");
    const once=Boolean(state.scene?.static_pulse||rhythmActive()),matches=once?result.finite_once:result.finite_expected;
    log(`芯片 SDO 回读：${values}`,matches?"success":"error");
    log(matches?`影子寄存器符合每次触发播放 ${once?1:result.expected_pattern_repeats} 遍的配置；仍需示波器核对输出。`:"影子寄存器不符合当前有限次数配置，请保留上述读值。",matches?"success":"error");
  }catch(error){log(`回读失败：${error.message}`,"error")}
  finally{state.busy=false;updateControls()}
});
el("sendScene").addEventListener("click",send);
el("abortOutput").addEventListener("click",abort);
el("saveScene").addEventListener("click",save);
el("downloadScene").addEventListener("click",download);
el("syncPairs").addEventListener("click",syncPairs);
el("staticPair34").addEventListener("click",configureStaticPair34);
el("importScene").addEventListener("click",()=>el("sceneFile").click());
el("sceneFile").addEventListener("change",async event=>{
  const file=event.target.files?.[0];if(!file)return;
  try{applyScene(JSON.parse(await file.text()));log(`已导入 ${file.name}，请检查预览后再发送。`,"success")}
  catch(error){log(`导入失败：${error.message}`,"error")}
  event.target.value="";
});
window.addEventListener("resize",()=>{if(state.preview)renderPreview(state.preview)});

(async()=>{
  try{
    const data=await api("/api/bootstrap");state.catalog=data.catalog;
    applyScene(data.scene);
    await refreshPorts();
    state.portTimer=setInterval(refreshPorts,6000);
    log("控制台已启动。选择模式、检查四路波形，检测串口后即可一次发送。","success");
  }catch(error){log(`启动失败：${error.message}`,"error");showPreviewError(error.message)}
})();
