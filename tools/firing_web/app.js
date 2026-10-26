"use strict";

const el=id=>document.getElementById(id);
const modesZh=["持续放电","起始放电","持续簇发","起始簇发","混合模式","频率适应", "I 类兴奋性","II 类兴奋性","发放延迟","阈下振荡","共振器","积分器", "反跳单发","反跳簇发","阈值可变性","双稳态","去极化后电位","适应性", "抑制诱发放电","抑制诱发簇发","全或无","不应期","兴奋性阻断"];
const paramLabels={period_us:"模板长度 / us",start_us:"开始时刻 / us",width_us:"脉冲宽度 / us",rise_us:"上升沿 / us",fall_us:"下降沿 / us",ramp_us:"斜坡时长 / us",gap_us:"双脉冲间隔 / us",pulse_period_us:"脉冲列间隔 / us",pulse_count:"脉冲列数量",gate_sine_period_us:"Gate 正弦周期 / us",gate_floor_v:"Gate 最低电压 / V",gate_initial_v:"Gate 初始电压 / V",gate_final_v:"Gate 末段电压 / V",gate_baseline_v:"Gate 基线电压 / V",levels_v:"三档电压 / V（逗号分隔）"};
const extraLabels={vin_width_us:"Vin 脉宽（含边沿）/ μs",gate_width_us:"Vgate 脉宽（含边沿）/ μs",
  pulse_gap_us:"脉冲间隔（回到基线后）/ μs",vin_frequency_khz:"Vin 内部方波频率 / kHz",
  vin_duty_percent:"Vin 内部方波占空比 / %",gate_frequency_khz:"Vgate 正弦频率 / kHz",
  pulse_count:"脉冲数量",gate_initial_v:"Vgate 开始电压 / V",gate_final_v:"Vgate 结束电压 / V",
  stage1_voltage_v:"第一段电压 / V",stage2_voltage_v:"第二段电压 / V",
  first_stage_us:"第一段持续时间 / μs",second_stage_us:"第二段持续时间 / μs",
  level_low_v:"第一档电压 / V",level_mid_v:"第二档电压 / V",level_high_v:"第三档电压 / V"};
const extraKeys=Object.keys(extraLabels);
Object.assign(paramLabels,extraLabels);
const state={catalog:null,scene:null,connectedPort:null,preview:null,previewTimer:null,previewToken:0,busy:false,jobId:null,portTimer:null};
paramLabels.duty_percent="方波占空比 / %";

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

function createEditor(number,binding){
  const card=document.createElement("article");card.className="channel-card";card.dataset.channel=number;
  card.innerHTML=`<div class="channel-top"><div class="channel-name"><span class="channel-icon">${String(number).padStart(2,"0")}</span>DAC${number}</div><label class="switch-label"><input type="checkbox" data-field="enabled">启用通道</label></div>
    <div class="channel-grid">
      <div class="field"><label>拓扑</label><select data-field="topology"></select></div>
      <div class="field"><label>模式</label><select data-field="mode"></select></div>
      <div class="field"><label>输入信号</label><select data-field="signal"><option value="vin">Vin</option><option value="gate">Vgate</option></select></div>
      <div class="field"><label>同步配对</label><select data-field="pair"><option value="">无</option><option value="A">A</option><option value="B">B</option></select></div>
      <div class="field wide"><label>实验变体 · 同图不同曲线逐一编号</label><select data-field="variant"></select></div>
      <div class="field"><label>序列分段</label><select data-field="component"></select></div>
      <div class="field"><label>包络频率 / kHz</label><input data-field="frequency" type="number" min="0.001" step="any" inputmode="decimal"></div>
      <div class="field"><label>幅值 / V（绝对峰值）</label><div class="inline"><input data-field="amplitude" type="number" min="0" max="10" step="any"><button class="reference-button" data-action="peak" type="button">原图幅值</button></div></div>
      <div class="field"><label>偏移 / V</label><input data-field="offset" type="number" step="any"></div>
      <div class="field"><label>相位 / °</label><input data-field="phase" type="number" step="any"></div>
    </div><p class="pair-note" role="status"></p><p class="channel-note"></p><div class="simple-params advanced-grid"></div><p class="simple-hint channel-note"></p><details class="advanced"><summary>高级时序参数</summary><div class="advanced-grid"></div></details>`;
  const field=name=>card.querySelector(`[data-field="${name}"]`);
  for(const t of [3,5,6,7])option(field("topology"),t,`拓扑 ${t}`);
  for(let m=1;m<=23;m++)option(field("mode"),m,`${String(m).padStart(2,"0")} ${modesZh[m-1]}`);
  option(field("mode"),24,"24 静态扫描（Vin 单脉冲 / Vgate 恒压）");
  option(field("mode"),25,"25 标准方波（支持 1 kHz）");
  option(field("mode"),26,"26 标准正弦（支持 1 kHz）");
  const advanced=card.querySelector(".advanced .advanced-grid");
  for(const [key,label] of Object.entries(paramLabels)){
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=label;
    const input=document.createElement("input");input.dataset.param=key;input.type="text";
    input.placeholder=key==="levels_v"?"例如 3, 4.7, 5":"模板默认";
    if(extraKeys.includes(key)){
      input.type="number";input.step="any";input.placeholder="留空沿用原模板";
      input.setAttribute("aria-label",label);
      if(!key.endsWith("_v"))input.min="0";
      if(key==="pulse_count"){input.min="1";input.max="1000";input.step="1"}
      if(key==="vin_duty_percent")input.max="100";
    }
    wrap.append(lab,input);(extraKeys.includes(key)?card.querySelector(".simple-params"):advanced).append(wrap);
  }
  field("enabled").checked=binding.enabled!==false;
  choose(field("topology"),binding.topology??6);choose(field("mode"),binding.mode??3);
  choose(field("signal"),binding.signal??"vin");choose(field("pair"),binding.pair??"");
  updateVariantChoices(card,binding.variant??0,binding.component);
  field("frequency").value=Number(binding.frequency_hz??(Number(binding.mode)>=25?1000:100000))/1000;
  field("amplitude").value=binding.amplitude_v??peakFor(card);
  field("offset").value=binding.offset_v??0;field("phase").value=binding.phase_deg??0;
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
  field("frequency").closest(".field").querySelector("label").textContent=basic?"波形频率 / kHz":"包络频率 / kHz";
  field("phase").disabled=mode===25;
  card.querySelector(".advanced").hidden=mode===26;
  for(const input of card.querySelectorAll("[data-param]"))
    input.closest(".field").hidden=basic?!(mode===25&&input.dataset.param==="duty_percent"):input.dataset.param==="duty_percent";
  if(mode===25){
    const duty=card.querySelector('[data-param="duty_percent"]');if(!duty.value)duty.value=50;
    field("phase").value=0;card.querySelector(".advanced").open=true;
  }
  if(Number(field("mode").value)===24){
    const isVin=field("signal").value==="vin";
    card.querySelector('[data-action="peak"]').hidden=true;
    field("amplitude").closest(".field").querySelector("label").textContent=isVin?"Vin 脉冲电压 / V":"Vgate 恒定电压 / V";
    card.querySelector(".channel-note").textContent=isVin?
      "本通道输出 Vin：调“Vin 脉冲电压”和下方“脉冲宽度 / us”。":
      "本通道输出 Vgate 恒压：调“Vgate 恒定电压”。";
    card.querySelector(".advanced").open=true;
    field("frequency").closest(".field").hidden=true;
    for(const [name,value] of [["period_us",100],["start_us",10],["width_us",10]]){
      const input=card.querySelector(`[data-param="${name}"]`);
      if(!input.value)input.value=value;
    }
    for(const name of ["start_us","width_us"])
      card.querySelector(`[data-param="${name}"]`).closest(".field").hidden=!isVin;
  }else{
    card.querySelector('[data-action="peak"]').hidden=false;
    field("frequency").closest(".field").hidden=false;
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
  const visible={vin_width_us:firing&&vin&&![7,11,12].includes(mode),gate_width_us:firing&&!vin&&hasGateWidth,
    pulse_gap_us:(mode===3&&!vin)||([20,22].includes(mode)&&vin),vin_frequency_khz:[11,12].includes(mode)&&vin,
    vin_duty_percent:[11,12].includes(mode)&&vin,gate_frequency_khz:mode===11&&!vin,
    pulse_count:(mode===3&&!vin)||([11,12,20].includes(mode)&&vin),
    gate_initial_v:mode===6&&!vin,gate_final_v:mode===6&&!vin,
    stage1_voltage_v:stages,stage2_voltage_v:stages,first_stage_us:stages,second_stage_us:stages,
    level_low_v:levels,level_mid_v:levels,level_high_v:levels};
  for(const key of extraKeys)card.querySelector(`[data-param="${key}"]`).closest(".field").hidden=!visible[key];
  const countInput=card.querySelector('[data-param="pulse_count"]'),countLabel=vin?"Vin 脉冲数量":"Vgate 脉冲数量";
  countInput.setAttribute("aria-label",countLabel);countInput.closest(".field").querySelector("label").textContent=countLabel;
  card.querySelector(".simple-params").hidden=!firing;
  const hint=card.querySelector(".simple-hint");hint.hidden=!firing;
  hint.textContent=mode===12&&!vin?"Vgate 为恒压，只需设置上方幅值；Vin 的脉宽和间隔不会改变 Gate。":
    "脉宽、间隔填写实际 μs，互不挤占；留空沿用原模板。";
  if([11,12].includes(mode))hint.textContent=vin?
    "这里设置脉冲列内部的方波频率和占空比，脉宽 = 周期 × 占空比；上方包络频率只控制整组时窗。留空沿用当前变体。":
    mode===11?"Vgate 输出连续正弦，正弦频率独立于 Vin 内部方波频率。":"Vgate 为恒压，只需设置上方电压。";
  if(stages)hint.textContent=mode===7?"第一段从 0 V 斜坡升至第一段电压，再以第二段电压保持；两段时间分别填写实际 μs。":
    topology===7?"第一段方波接第二段方波；两段电压和时间分别设置，时间填写实际 μs。":
    "第一段从第一段电压斜坡变化至第二段电压，第二段保持；两段时间分别填写实际 μs。";
  if(mode===6&&!vin)hint.textContent="Vgate 从开始电压斜坡变化至结束电压；脉宽设置斜坡持续时间（实际 μs）。";
  if(levels)hint.textContent+=" 三档电压分别填写，数值不再乘以幅值；通道偏移仍会叠加。";
  if(mode===12&&vin)hint.textContent+=" 快、慢脉冲通过实验变体分别测试，每次只输出一组。";
  if(firing){
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
  if(mode===12&&!vin)field("amplitude").closest(".field").querySelector("label").textContent="Vgate 恒定电压 / V";
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
    note.textContent=peer?`已配对 DAC${peer.dataset.channel} · 模式自动联动`:"当前未配对";
    note.classList.toggle("unpaired",!peer);
  }
}

function resetMode(card){
  for(const input of card.querySelectorAll("[data-param]"))input.value="";
  updateVariantChoices(card,0,null);
  if(Number(card.querySelector('[data-field="mode"]').value)>=25){
    card.querySelector('[data-field="frequency"]').value=1;
    card.querySelector('[data-field="phase"]').value=0;
  }
  card.querySelector('[data-field="amplitude"]').value=peakFor(card);
  card.dataset.previousMode=card.querySelector('[data-field="mode"]').value;
}

function syncExtraParameter(card,input){
  const key=input.dataset.param;
  if(!extraKeys.includes(key))return;
  const peer=pairedPeer(card);
  if(peer){
    peer.querySelector(`[data-param="${key}"]`).value=input.value;
    updateSimpleControls(peer);
  }
}

function applyScene(scene){
  if(!scene||!Array.isArray(scene.channels))throw new Error("场景 JSON 缺少 channels 数组");
  state.scene=scene;
  el("intervalSeconds").value=scene.interval_s??1;
  el("repeatCount").value=scene.repeat_count??1;
  const host=el("channelEditors");host.replaceChildren();
  for(let n=1;n<=4;n++){
    host.append(createEditor(n,scene.channels.find(c=>Number(c.channel)===n)||{channel:n,enabled:false}));
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
    const n=Number(card.dataset.channel),params={};
    for(const input of card.querySelectorAll("[data-param]")){
      const text=input.value.trim(),key=input.dataset.param;
      const mode=Number(f("mode").value);
      if((mode===25&&key!=="duty_percent")||mode===26||(mode<25&&key==="duty_percent"))continue;
      if(!text)continue;
      if(key==="levels_v"){
        const bits=text.split(",").map(p=>p.trim());
        if(bits.length!==3)throw new Error(`DAC${n} 三档电压需要三个数`);
        params[key]=bits.map(p=>number(p,`DAC${n} 三档电压`));
      }else{
        params[key]=number(text,`DAC${n} ${paramLabels[key]}`);
        if(key==="pulse_count"&&!Number.isInteger(params[key]))throw new Error(`DAC${n} 脉冲列数量应为整数`);
      }
    }
    if(params.vin_frequency_khz!==undefined||params.pulse_gap_us!==undefined)delete params.pulse_period_us;
    if(params.pulse_gap_us!==undefined)delete params.gap_us;
    if(params.vin_duty_percent!==undefined){delete params.vin_width_us;delete params.width_us;delete params.pulse_gap_us}
    if(params.gate_frequency_khz!==undefined)delete params.gate_sine_period_us;
    if(params.first_stage_us!==undefined||params.second_stage_us!==undefined){delete params.ramp_us;delete params.width_us}
    if(Number(f("mode").value)===6&&params.gate_width_us!==undefined)delete params.ramp_us;
    const channel={channel:n,enabled:f("enabled").checked,topology:Number(f("topology").value),
      mode:Number(f("mode").value),signal:f("signal").value,variant:Number(f("variant").value),
      component:f("component").value,frequency_hz:number(f("frequency").value,`DAC${n} 包络频率`)*1000,
      amplitude_v:number(f("amplitude").value,`DAC${n} 幅值`),offset_v:number(f("offset").value,`DAC${n} 偏移`),
      phase_deg:number(f("phase").value,`DAC${n} 相位`)};
    if(channel.mode===24){
      const period=params.period_us??100;
      if(period<=0)throw new Error(`DAC${n} 静态扫描时窗必须大于 0`);
      channel.frequency_hz=1000000/period;
    }
    if(f("pair").value)channel.pair=f("pair").value;
    if(Object.keys(params).length)channel.parameters=params;
    return channel;
  });
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
  for(const id of ["frameFreq","memoryUsed","timingValue"])el(id).textContent="—";
  updateControls();
}

function formatHz(value){
  if(!value)return"直流";
  return value>=1000?`${(value/1000).toLocaleString("zh-CN",{maximumFractionDigits:4})} kHz`:
    `${value.toLocaleString("zh-CN",{maximumFractionDigits:4})} Hz`;
}

function renderPreview(result){
  el("previewFlag").textContent=result.ok?"可发送":"需要调整";
  el("previewFlag").className=`pill ${result.ok?"good":"bad"}`;
  el("previewError").hidden=result.ok;
  el("previewError").textContent=result.ok?"":`当前配置无法一起发送：${result.error}。下图仅用于检查单路形状，修正后会重新编译。`;
  el("frameFreq").textContent=result.ok?formatHz(result.summary.frame_hz):"—";
  el("memoryUsed").textContent=result.ok?`${result.summary.sram_words} / 4096 点`:"—";
  el("timingValue").textContent=result.ok?`${result.summary.hold} / ${result.summary.frequency_error_ppm.toFixed(3)} ppm`:"—";
  const host=el("charts");host.replaceChildren();
  for(const row of result.channels){
    const card=document.createElement("article");card.className="chart-card";
    const head=document.createElement("div");head.className="chart-head";
    const title=document.createElement("strong");title.textContent=`DAC${row.channel} · ${row.signal==="gate"?"Vgate":row.signal==="vin"?"Vin":"未启用"}`;
    const freq=document.createElement("small");freq.textContent=formatHz(row.frequency_hz);
    head.append(title,freq);
    const canvas=document.createElement("canvas");canvas.setAttribute("aria-label",`DAC${row.channel} 波形图`);
    const meta=document.createElement("div");meta.className="chart-meta";
    meta.textContent=row.error?row.error:row.source==="template"?"理论波形 · 当前配置不可发送（原因见上方）":
      row.source==="constant"?`直流 · ${Number(row.min_v).toFixed(3)} V*`:
      row.source==="disabled"?"零码 / 通道未启用":
      `T${row.topology} / ${String(row.mode).padStart(2,"0")} · ${row.min_v.toFixed(3)}…${row.max_v.toFixed(3)} V*${row.snapped?` · 窄平台量化 ${row.snapped} 点`:""}`;
    if(row.zero_tail_samples)meta.textContent+=` · 末尾 ${row.zero_tail_us.toFixed(2)} us 零码等待由芯片计时`;
    if(row.source==="dds")meta.textContent+=" · DDS 实际频率 · 曲线为解析预览";
    if(row.source==="fpga_square")meta.textContent+=" · FPGA 定时切换电平";
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
  el("intervalSeconds").disabled=state.busy;
  el("repeatCount").disabled=state.busy;
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
      for(const key of ["topology","mode","variant","component","frequency_hz","phase_deg","parameters"]){
        if(source[key]===undefined)delete target[key];else target[key]=JSON.parse(JSON.stringify(source[key]));
      }
      target.enabled=source.enabled;target.signal=source.signal==="vin"?"gate":"vin";
      target.offset_v=0;source.pair=label;target.pair=label;
      const e=entry(target.topology,target.mode),c=e.cases.find(x=>x.variant===target.variant);
      target.amplitude_v=Math.min(10,Math.max(...c[`${target.signal}_range_v`].map(Math.abs)));
    }
    applyScene(scene);log("两组配对的拓扑、模式、实验、分段、频率和相位已同步。","success");
  }catch(error){log(`配对失败：${error.message}`,"error")}
}

function configureStaticPair34(){
  const scene={...(state.scene||{})};
  const old=Array.isArray(scene.channels)?scene.channels:[];
  scene.channels=[1,2].map(n=>({...old.find(c=>Number(c.channel)===n),channel:n,enabled:false}));
  for(const [channel,signal,amplitude] of [[3,"vin",1],[4,"gate",0]]){
    scene.channels.push({channel,enabled:true,topology:6,mode:24,signal,
      variant:0,component:"pulse",frequency_hz:10000,amplitude_v:amplitude,
      offset_v:0,phase_deg:0,pair:"B",
      parameters:{period_us:100,start_us:10,width_us:10}});
  }
  scene.interval_s=1;scene.repeat_count=1;
  applyScene(scene);
  log("已设 DAC3=Vin 单脉冲、DAC4=Vgate 恒压。请分别调整两张卡的电压，并在 DAC3 调脉宽。","success");
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
        for(const key of ["vin_frequency_khz","vin_duty_percent","vin_width_us","pulse_gap_us","pulse_period_us","width_us"])
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
  syncExtraParameter(card,event.target);updateSimpleControls(card);
  updatePairStatus();
  schedulePreview();
});
el("channelEditors").addEventListener("input",event=>{
  const card=event.target.closest(".channel-card");
  if(card){syncExtraParameter(card,event.target);updateSimpleControls(card)}
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
    log(`芯片 SDO 回读：${values}`,result.finite_expected?"success":"error");
    log(result.finite_expected?`影子寄存器符合每次触发播放 ${result.expected_pattern_repeats} 遍的配置；仍需示波器核对输出。`:"影子寄存器不符合当前有限次数配置，请保留上述读值。",result.finite_expected?"success":"error");
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
