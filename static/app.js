const $ = id => document.getElementById(id);
const labels = {running:'生成中',completed:'已生成',failed:'失败',not_sent:'未发送',not_configured:'未配置邮件',sending:'发送中',sent:'已发送',unknown:'投递结果未知'};
const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
const day = value => new Date(value).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'});
let users=[], selected='', currentRun='', runData=null, baseline='', polling, revision=0, busy=false, activeRun='', saving=false;
function storage(key,value) {try {if(value===undefined)return localStorage.getItem(key);localStorage.setItem(key,value);}catch(_){}}
async function api(path,options={}) {
  let response;
  try {response=await fetch('/api'+path,{headers:{'Content-Type':'application/json'},...options});}catch(_){throw new Error('无法连接服务，请检查服务是否运行。');}
  let data;try {data=await response.json();}catch(_){throw new Error('服务返回异常，请稍后重试。');}
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:response.status===422?'请检查邮箱格式及订阅字段长度。':'请求失败，请稍后重试。');
  return data;
}
function notify(text,error=false){$('notice').textContent=text;$('notice').hidden=!text;$('notice').dataset.error=String(error);}
function formMessage(text,error=false){$('form-message').textContent=text;$('form-message').classList.toggle('error',error);}
function openPanel(id){const other=id==='settings-panel'?'history-panel':'settings-panel';if($(other).open)$(other).close();if(!$(id).open)$(id).showModal();}
const split=id=>$(id).value.split(/[,，、]/).map(x=>x.trim()).filter(Boolean);
function profile(){return {nickname:$('nickname').value.trim(),email:$('email').value.trim(),topics:split('topics'),keywords:split('keywords'),excluded_keywords:split('excluded'),send_time:$('time').value,enabled:$('enabled').checked};}
function dirty(){return JSON.stringify(profile())!==baseline;}
function updateSaveState(){
  const changed=dirty();
  $('save-state').textContent=saving?'保存中…':changed?'未保存':selected?'已保存':'尚未创建订阅';
  $('save-profile').disabled=saving||!!selected&&!changed;
  $('save-profile').textContent=saving?'保存中…':'保存订阅';
  $('discard').hidden=!changed;$('discard').disabled=saving;
}
function updateDirty(){
  updateSaveState();formMessage('');
  $('time').disabled=!$('enabled').checked;
  $('schedule-fields').hidden=!$('enabled').checked;
}
function updateControls(){
  $('generate').disabled=!selected||busy||!!activeRun;
  $('generate').textContent=activeRun?'正在生成…':busy?'提交中…':'立即生成';
}
function summary(){
  const p=users.find(x=>x.id===selected);
  const topics=p?[...p.topics,...p.keywords].slice(0,3).join('、')||'AI 综合新闻':'未设置';
  $('subscription-summary').textContent=p?topics+' · '+(p.enabled?'每天 '+p.send_time+' 推送':'每日推送已暂停'):'先设置你的关注偏好';
  $('subscription-summary').title=$('subscription-summary').textContent;
}
function populate(){
  const p=users.find(x=>x.id===selected);
  $('nickname').value=p?.nickname||'';$('email').value=p?.email||'';$('topics').value=(p?.topics||[]).join('、');
  $('keywords').value=(p?.keywords||[]).join('、');$('excluded').value=(p?.excluded_keywords||[]).join('、');
  $('time').value=p?.send_time||'09:00';$('enabled').checked=p?.enabled??false;
  $('profile-owner').textContent=p?.nickname||'新用户';
  baseline=JSON.stringify(profile());updateDirty();summary();
}
function saveReadingPosition(){if(currentRun)storage('scroll:'+currentRun,String($('content').scrollTop));}
async function selectUser(id){
  if(dirty()){$('users').value=selected;openPanel('settings-panel');formMessage('请先保存修改，或选择“放弃修改”后切换用户。',true);return;}
  saveReadingPosition();clearTimeout(polling);revision++;selected=id;currentRun='';runData=null;activeRun='';$('users').value=id;
  storage('user',id);populate();updateControls();notify('');renderEmpty();
  const rows=await loadHistory();
  if(selected!==id||!rows.length)return;
  const saved=storage('run:'+id);const target=rows.find(r=>r.id===saved)?.id||rows[0].id;
  await showRun(target);
}
async function loadUsers(){
  users=await api('/users');
  $('users').innerHTML='<option value="">新用户</option>'+users.map(u=>'<option value="'+u.id+'">'+escape(u.nickname)+'</option>').join('');
  $('users').value=selected;
}
async function loadHistory(){
  if(!selected){$('history').innerHTML='<p class="muted">创建订阅后可查看历史。</p>';return [];}
  const uid=selected,rows=await api('/users/'+uid+'/runs');if(uid!==selected)return [];
  activeRun=rows.find(r=>r.status==='running')?.id||'';updateControls();
  $('history').innerHTML=rows.length?rows.map(r=>'<button class="history-item '+(r.id===currentRun?'active':'')+'" data-id="'+r.id+'"><strong>'+escape(day(r.created_at))+' · AI 简报</strong><span>'+escape(date(r.created_at))+' · '+escape(labels[r.status])+' · '+escape(labels[r.delivery]||r.delivery)+'</span></button>').join(''):'<p class="muted">还没有简报。点击“立即生成”开始。</p>';
  $('history').querySelectorAll('button').forEach(b=>b.onclick=()=>{showRun(b.dataset.id).then(()=>$('history-panel').close()).catch(e=>notify(e.message,true));});
  return rows;
}
function renderEmpty(){
  $('reader').innerHTML='<div class="empty"><span class="eyebrow">每天，留一点时间给新消息</span><h1>'+(selected?'你的下一份 AI 简报':'从你关注的 AI 话题开始')+'</h1><p>'+(selected?'点击“立即生成”，或从历史记录中继续阅读。':'设置话题和关键词，让 Agent 为你整理一份带来源的新闻简报。')+'</p>'+(!selected?'<button id="start-settings">设置订阅</button>':'')+'</div>';
  if($('start-settings'))$('start-settings').onclick=()=>openPanel('settings-panel');
}
function summaryPoints(text){
  // Split existing Chinese sentences only; preserve every word and trailing content.
  const points=String(text||'').match(/[^。！？]+[。！？]*|[。！？]+/g)||[];
  const clean=points.map(x=>x.trim()).filter(Boolean);
  return clean.length>4?[...clean.slice(0,3),clean.slice(3).join('')]:clean;
}
function articleHTML(item,index){
  const points=summaryPoints(item.summary);
  const summary=points.length>1?'<ul class="takeaways">'+points.map(p=>'<li>'+escape(p)+'</li>').join('')+'</ul>':'<p class="takeaway">'+escape(item.summary)+'</p>';
  return '<article class="article"><div class="article-heading"><span class="article-number" aria-label="第 '+(index+1)+' 条">'+String(index+1).padStart(2,'0')+'</span><h2>'+escape(item.title)+'</h2></div>'+summary+
    '<div class="article-footer"><dl class="article-facts"><div><dt>来源</dt><dd>'+escape(item.source)+'</dd></div><div><dt>发布</dt><dd>'+escape(date(item.published_at))+'</dd></div></dl><a href="'+escape(item.url)+'" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></div>'+
    '<details class="reason-details" data-detail="reason-'+index+'"><summary>入选理由</summary><p>'+escape(item.reason)+'</p></details></article>';
}
function deliveryHTML(r){
  const email=users.find(x=>x.id===selected)?.email||'';
  if(r.brief?.is_demo)return '<div class="delivery-row"><p>离线模拟简报，不发送邮件。</p></div>';
  const hints={sent:'发件服务器已接受投递。如未收到，请检查垃圾邮件。',sending:'正在提交到发件服务器，请稍候。',unknown:'无法确定服务器是否已接收。请先检查邮箱，避免重复发送。',failed:'本次投递失败。请检查邮件配置；此记录不会自动重发。',not_configured:'发件服务器尚未配置，配置并重启服务后可发送。'};
  const blocked=['sent','sending','unknown','failed'].includes(r.delivery);
  const button=blocked?'<strong>'+escape(labels[r.delivery])+'</strong>':'<button id="send-mail" class="secondary">发送这份简报</button>';
  const text=blocked?hints[r.delivery]:'收件地址：'+email+(r.delivery==='not_configured'?' · '+hints.not_configured:'');
  const err=r.delivery_detail?.error?'（'+r.delivery_detail.error+'）':'';
  if(r.delivery==='sent')return '<div class="delivery-row"><p class="delivery-status"><span class="fact-label">邮件</span>'+button+'</p><details class="delivery-details" data-detail="delivery"><summary>投递说明</summary><p>'+escape(text)+'</p></details></div>';
  return '<div class="delivery-row"><p>'+escape(text)+escape(err)+'</p>'+button+'</div>';
}
function renderRun(r){
  const b=r.brief,scroll=$('content').scrollTop;
  const opened=new Set([...document.querySelectorAll('#reader details[open][data-detail]')].map(d=>d.dataset.detail));
  const sources=b?new Set(b.items.map(i=>i.source)).size:0;
  let body='<header class="brief-header"><div class="brief-title-row"><h1>'+(b?.is_demo?'离线示例 · 非真实新闻':r.status==='running'?'正在整理你的 AI 简报':r.status==='failed'?'本次简报生成失败':'AI 新闻简报')+'</h1><time datetime="'+escape(r.created_at)+'">'+escape(day(r.created_at))+'</time></div>';
  if(b)body+='<dl class="brief-facts"><div><dt>本期入选</dt><dd>'+b.items.length+' 条新闻</dd></div><div><dt>新闻来源</dt><dd>'+sources+' 个</dd></div><div><dt>时间范围</dt><dd>'+(b.is_demo?'模拟数据':'生成前 24 小时')+'</dd></div></dl>';
  if(r.error)body+='<p class="feedback error">'+escape(r.error)+'</p>';
  if(!b)body+='<p class="muted">'+(r.status==='running'?'Agent 正在自主选择工具、获取材料和筛选内容。':'可检查错误原因后，再点击“立即生成”。')+'</p>';
  if(b?.is_demo)body+='<p class="feedback">模拟数据，不代表真实新闻或模型调用。</p>';
  body+='</header>';
  if(b){
    body+=b.items.map(articleHTML).join('');
    if(!b.items.length)body+='<p class="muted">本次没有匹配的新闻。你可以在订阅设置中调整关注范围。</p>';
    body+=deliveryHTML(r);
    body+='<details class="collection-details" data-detail="collection"><summary>采集说明</summary><div><dl class="collection-facts"><div><dt>生成时间</dt><dd>'+escape(date(r.created_at))+' · 北京时间</dd></div><div><dt>摘要依据</dt><dd>公开 RSS 摘要，非全文</dd></div></dl><p>'+escape(b.note)+'</p></div></details>';
  }
  body+='<details id="tool-details" data-detail="tools"><summary>工具调用记录 <span class="detail-count">'+r.tools.length+' 次</span></summary><div class="tool-list">'+(r.tools.map(t=>'<div class="tool"><strong>'+escape(t.name)+'</strong><span class="meta"> · '+t.duration.toFixed(2)+' 秒</span><pre>参数：'+escape(t.arguments)+'\n结果：'+escape(t.result)+'</pre></div>').join('')||'<p class="muted">暂无工具调用。</p>')+'</div></details>';
  $('reader').innerHTML=body;
  document.querySelectorAll('#reader details[data-detail]').forEach(d=>{d.open=opened.has(d.dataset.detail);});
  $('content').scrollTop=scroll;
  if($('send-mail'))$('send-mail').onclick=sendCurrent;
}
async function showRun(id){
  if(currentRun!==id){saveReadingPosition();$('content').scrollTop=0;}
  clearTimeout(polling);const token=++revision,uid=selected;currentRun=id;storage('run:'+uid,id);
  const r=await api('/users/'+uid+'/runs/'+id);
  if(token!==revision||uid!==selected||id!==currentRun)return;
  runData=r;renderRun(r);
  if(!$('content').scrollTop)$('content').scrollTop=Number(storage('scroll:'+id))||0;
  await loadHistory();
  if(token!==revision)return;
  if(r.status==='running'||r.delivery==='sending'||activeRun)polling=setTimeout(()=>showRun(id).catch(e=>notify(e.message,true)),2000);
}
function requireSaved(){
  if(!dirty())return true;
  openPanel('settings-panel');formMessage('有未保存修改。请先保存，确保使用当前邮箱和订阅偏好。',true);return false;
}
async function sendCurrent(){
  if(!requireSaved())return;
  const uid=selected,id=currentRun,button=$('send-mail');button.disabled=true;button.textContent='正在发送…';notify('');
  try {
    const result=await api('/users/'+uid+'/runs/'+id+'/send',{method:'POST'});
    if(selected===uid&&currentRun===id){await showRun(id);notify(result.delivery==='sent'?'邮件已提交到发件服务器。':labels[result.delivery]||result.delivery,result.delivery!=='sent');}
  }catch(e){notify(e.message,true);if(selected===uid&&currentRun===id){button.disabled=false;button.textContent='发送这份简报';}}
}
$('profile').addEventListener('input',updateDirty);$('profile').addEventListener('change',updateDirty);
$('discard').onclick=()=>{populate();formMessage('已恢复上次保存的配置。');};
$('settings-open').onclick=()=>openPanel('settings-panel');
$('history-open').onclick=()=>{openPanel('history-panel');loadHistory().catch(e=>notify(e.message,true));};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const rect=d.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)d.close();}}));
$('users').onchange=e=>selectUser(e.target.value).catch(e=>notify(e.message,true));
$('new-user').onclick=async()=>{if(!requireSaved())return;await selectUser('');openPanel('settings-panel');};
$('refresh').onclick=()=>loadHistory().catch(e=>notify(e.message,true));
$('profile').onsubmit=async e=>{
  e.preventDefault();if(saving||selected&&!dirty())return;saving=true;updateSaveState();
  try {
    const before=selected,result=await api(selected?'/users/'+selected:'/users',{method:selected?'PUT':'POST',body:JSON.stringify(profile())});
    selected=result.id;storage('user',selected);await loadUsers();populate();formMessage('订阅已保存。');
    if(before!==selected){currentRun='';runData=null;activeRun='';renderEmpty();await loadHistory();}
    else if(runData)renderRun(runData);
    updateControls();$('settings-panel').close();notify('订阅已保存。');
  }catch(e){formMessage(e.message,true);}finally{saving=false;updateSaveState();}
};
$('generate').onclick=async()=>{
  if(!requireSaved())return;
  const uid=selected;busy=true;updateControls();notify('');
  try {const r=await api('/users/'+uid+'/runs',{method:'POST'});if(uid===selected){activeRun=r.id;notify('任务已开始。手动生成不会自动发送邮件。');await showRun(r.id);}}
  catch(e){notify(e.message,true);}finally{busy=false;updateControls();}
};
$('content').addEventListener('scroll',saveReadingPosition,{passive:true});
(async()=>{try{
  const h=await api('/health');$('health').textContent=h.model+' · '+(h.model_configured?'密钥已配置':'未配置密钥')+' · '+(h.mail_configured?'邮件已配置':'未配置邮件');
  await loadUsers();baseline=JSON.stringify(profile());const saved=storage('user');
  await selectUser(users.some(u=>u.id===saved)?saved:users[0]?.id||'');
}catch(e){notify(e.message,true);}})();
