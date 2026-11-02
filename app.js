const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let overviewChart, reportChart, consumerChart, lastReport = null;
const today = new Date();
$('#reading-date').value = today.toISOString().slice(0,10);

async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
  const body = await response.json().catch(()=>({error:'Unexpected server response.'}));
  if (!response.ok) throw new Error(body.error || 'Request failed.');
  return body;
}
function toast(message, error=false) {
  const el=$('#toast'); el.textContent=message; el.className='toast show'+(error?' error':'');
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.className='toast',4000);
}
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function num(v){return Number(v||0).toLocaleString(undefined,{maximumFractionDigits:3});}
function emptyRow(cols,msg){return `<tr><td colspan="${cols}" class="empty-cell">${esc(msg)}</td></tr>`;}
function navigate(target){
  $$('.page').forEach(p=>p.classList.toggle('active',p.id===target));
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.target===target));
  const labels={dashboard:'Overview',consumers:'Consumers & meters',readings:'Meter readings',reports:'Analytics & reports'};
  $('#page-crumb').textContent=labels[target]||'Overview';
  if(target==='reports') loadReport();
}
$$('.nav-item').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.target)));
$$('[data-goto]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.goto)));

async function loadHealth(){
  try {const h=await api('/api/health');$('#db-status').textContent=`Connected · ${h.database}`;}
  catch(e){$('#db-status').textContent='Database unavailable';toast('Cannot connect to MySQL. Check .env and ensure MySQL is running.',true);}
}
async function loadOverview(){
  try{
    const d=await api('/api/overview');
    $('#stat-consumers').textContent=num(d.consumers);$('#stat-meters').textContent=num(d.active_meters);
    $('#stat-usage').textContent=num(d.monthly_kwh);$('#stat-readings').textContent=num(d.readings);
  }catch(e){toast(e.message,true);}
  try{
    const data=await api('/api/report?period='+$('#dashboard-period').value+'&threshold=500');
    drawOverview(data.trend);
  }catch(e){console.error(e);}
  try{
    const readings=await api('/api/readings');
    $('#recent-table').innerHTML=readings.length?readings.slice(0,6).map(r=>`<tr><td>${esc(r.consumer_name)}</td><td>${esc(r.meter_code)}</td><td>${esc(r.reading_date)}</td><td>${num(r.cumulative_kwh)}</td><td>kWh</td></tr>`).join(''):emptyRow(5,'No readings yet. Add your first meter reading.');
  }catch(e){$('#recent-table').innerHTML=emptyRow(5,e.message);}
}
function baseChartOptions(){return {responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{backgroundColor:'#253747',padding:11,displayColors:false}},scales:{x:{grid:{display:false},ticks:{color:'#8b97a5',font:{size:10}},border:{display:false}},y:{beginAtZero:true,grid:{color:'#edf1f4'},ticks:{color:'#8b97a5',font:{size:10}},border:{display:false}}}};}
function drawOverview(trend){
  const empty=!trend.length;$('#chart-empty').style.display=empty?'flex':'none';
  if(overviewChart)overviewChart.destroy();
  overviewChart=new Chart($('#overview-chart'),{type:'line',data:{labels:trend.map(x=>x.period),datasets:[{data:trend.map(x=>x.usage_kwh),borderColor:'#188064',backgroundColor:'rgba(24,128,100,.10)',fill:true,tension:.35,borderWidth:2,pointRadius:3,pointBackgroundColor:'#188064'}]},options:baseChartOptions()});
}
async function loadConsumers(){
  try{
    const [cs,ms]=await Promise.all([api('/api/consumers'),api('/api/meters')]);
    $('#consumer-count').textContent=`${cs.length} records`;
    $('#consumer-table').innerHTML=cs.length?cs.map(c=>`<tr><td>${esc(c.consumer_name)}</td><td>${esc(c.consumer_type)}</td><td>${esc(c.region)}</td><td>${c.meter_count}</td></tr>`).join(''):emptyRow(4,'No consumers registered yet.');
    $('#meter-consumer').innerHTML='<option value="">Select a consumer</option>'+cs.map(c=>`<option value="${c.consumer_id}">${esc(c.consumer_name)} · ${esc(c.region)}</option>`).join('');
    $('#meter-table').innerHTML=ms.length?ms.map(m=>`<tr><td>${esc(m.meter_code)}</td><td>${esc(m.consumer_name)}</td><td>${esc(m.region)}</td><td>${esc(m.installed_on||'—')}</td><td><span class="badge good">${esc(m.meter_status)}</span></td></tr>`).join(''):emptyRow(5,'No meters registered yet.');
    $('#reading-meter').innerHTML='<option value="">Select a meter</option>'+ms.map(m=>`<option value="${m.meter_id}">${esc(m.meter_code)} · ${esc(m.consumer_name)}</option>`).join('');
  }catch(e){toast(e.message,true);}
}
async function loadReadings(){
  try{
    const rs=await api('/api/readings');$('#reading-count').textContent=`${rs.length} readings`;
    $('#readings-table').innerHTML=rs.length?rs.map(r=>`<tr><td>${esc(r.reading_date)}</td><td>${esc(r.consumer_name)}</td><td>${esc(r.meter_code)}</td><td>${num(r.cumulative_kwh)} kWh</td><td>${esc(r.note||'—')}</td></tr>`).join(''):emptyRow(5,'No readings saved yet.');
  }catch(e){$('#readings-table').innerHTML=emptyRow(5,e.message);}
}
function formObject(form){return Object.fromEntries(new FormData(form).entries());}
$('#consumer-form').addEventListener('submit',async e=>{
  e.preventDefault();try{await api('/api/consumers',{method:'POST',body:JSON.stringify(formObject(e.target))});e.target.reset();toast('Consumer created successfully.');await Promise.all([loadConsumers(),loadOverview()]);}catch(err){toast(err.message,true);}
});
$('#meter-form').addEventListener('submit',async e=>{
  e.preventDefault();const data=formObject(e.target);if(!data.installed_on)delete data.installed_on;
  try{await api('/api/meters',{method:'POST',body:JSON.stringify(data)});e.target.reset();toast('Meter registered successfully.');await Promise.all([loadConsumers(),loadOverview()]);}catch(err){toast(err.message,true);}
});
$('#reading-form').addEventListener('submit',async e=>{
  e.preventDefault();const data=formObject(e.target);
  try{await api('/api/readings',{method:'POST',body:JSON.stringify(data)});const keepMeter=data.meter_id;e.target.reset();$('#reading-date').value=today.toISOString().slice(0,10);$('#reading-meter').value=keepMeter;toast('Meter reading saved successfully.');await Promise.all([loadReadings(),loadOverview()]);}catch(err){toast(err.message,true);}
});
$('#dashboard-period').addEventListener('change',()=>loadOverview());
$('#report-period').addEventListener('change',()=>$$('.range-field').forEach(el=>el.classList.toggle('show',$('#report-period').value==='range')));
$('#run-report').addEventListener('click',loadReport);
async function loadReport(){
  const period=$('#report-period').value, threshold=$('#threshold').value||'500';
  const params=new URLSearchParams({period,threshold});
  if(period==='range'){if($('#report-start').value)params.set('start',$('#report-start').value);if($('#report-end').value)params.set('end',$('#report-end').value);}
  try{
    const d=await api('/api/report?'+params.toString());lastReport=d;
    const trend=d.trend||[];
    $('#report-chart-empty').style.display=trend.length?'none':'flex';
    if(reportChart)reportChart.destroy();
    reportChart=new Chart($('#report-chart'),{type:'bar',data:{labels:trend.map(x=>x.period),datasets:[{data:trend.map(x=>x.usage_kwh),backgroundColor:'#70b7a0',borderRadius:5,maxBarThickness:38}]},options:baseChartOptions()});
    const top=[...(d.rows||[])].sort((a,b)=>b.usage_kwh-a.usage_kwh).slice(0,7);
    $('#consumer-chart-empty').style.display=top.length?'none':'flex';
    if(consumerChart)consumerChart.destroy();
    consumerChart=new Chart($('#consumer-chart'),{type:'bar',data:{labels:top.map(x=>x.consumer_name+' · '+x.meter_code),datasets:[{data:top.map(x=>x.usage_kwh),backgroundColor:'#b8a8ef',borderRadius:5,maxBarThickness:25}]},options:{...baseChartOptions(),indexAxis:'y',scales:{x:{beginAtZero:true,grid:{color:'#edf1f4'},ticks:{color:'#8b97a5',font:{size:10}},border:{display:false}},y:{grid:{display:false},ticks:{color:'#687688',font:{size:10}},border:{display:false}}}}});
    $('#high-count').textContent=`${d.high_usage.length} flagged`;
    $('#high-table').innerHTML=d.high_usage.length?d.high_usage.map(r=>`<tr><td>${esc(r.period_label)}</td><td>${esc(r.consumer_name)}</td><td>${esc(r.meter_code)}</td><td>${num(r.usage_kwh)} kWh</td><td><span class="badge warn">High usage</span></td></tr>`).join(''):emptyRow(5,'No usage exceeded the configured threshold.');
    $('#validation-count').textContent=`${d.validation.length} issues`;
    $('#validation-table').innerHTML=d.validation.length?d.validation.map(v=>`<tr><td>${esc(v.consumer_name)}</td><td>${esc(v.meter_code)}</td><td>${esc(v.earlier_date)} · ${num(v.earlier_kwh)} kWh</td><td>${esc(v.later_date)} · ${num(v.later_kwh)} kWh</td><td><span class="badge warn">${esc(v.issue)}</span></td></tr>`).join(''):emptyRow(5,'No cumulative-reading decreases found.');
  }catch(e){toast(e.message,true);}
}
$('#export-csv').addEventListener('click',()=>{
  if(!lastReport){toast('Run a report before exporting.',true);return;}
  const rows=[['Period','Consumer','Type','Region','Meter','Usage_kWh'],...lastReport.rows.map(r=>[r.period_label,r.consumer_name,r.consumer_type,r.region,r.meter_code,r.usage_kwh])];
  const csv=rows.map(row=>row.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download='electricity-consumption-report.csv';a.click();URL.revokeObjectURL(url);
});
(async function init(){await loadHealth();await Promise.all([loadConsumers(),loadReadings(),loadOverview()]);await loadReport();})();
