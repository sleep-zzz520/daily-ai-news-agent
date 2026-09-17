const $ = id => document.getElementById(id);
let users = [], selected = '', currentRun = '', polling;
const labels = {running:'生成中',completed:'已生成',failed:'生成失败',not_sent:'未发送',not_configured:'未配置邮件',sending:'发送中',sent:'邮件已发送',unknown:'投递结果未知'};
const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, options={}) {
  const response = await fetch('/api'+path, {headers:{'Content-Type':'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : '请检查表单内容（每项不超过100字、最多30项）。');
  return data;
}
const notify = text => {$('message').textContent=text;};
const split = id => $(id).value.split(/[,，、]/).map(x=>x.trim()).filter(Boolean);
function selectUser(id) {
  selected=id; currentRun=''; clearTimeout(polling); $('users').value=id;
  const p=users.find(u=>u.id===id);
  $('nickname').value=p?.nickname||''; $('email').value=p?.email||'';
  $('topics').value=(p?.topics||[]).join('、'); $('keywords').value=(p?.keywords||[]).join('、');
  $('excluded').value=(p?.excluded_keywords||[]).join('、'); $('time').value=p?.send_time||'09:00'; $('enabled').checked=p?.enabled??true;
  $('generate').disabled=!id; $('reader').innerHTML='<p class="muted">选择一份历史简报，或立即生成。</p>';
  notify(''); loadHistory().catch(e=>notify(e.message));
}
async function loadUsers() {
  users=await api('/users');
  $('users').innerHTML='<option value="">新用户</option>'+users.map(u=>`<option value="${u.id}">${escape(u.nickname)}</option>`).join('');
}
async function loadHistory() {
  if (!selected) {$('history').innerHTML='<p class="muted">尚未选择用户。</p>';return;}
  const uid=selected, rows=await api(`/users/${uid}/runs`);
  if (uid!==selected) return;
  $('history').innerHTML=rows.length ? rows.map(r=>`<button class="history-item ${r.id===currentRun?'active':''}" data-id="${r.id}">${escape(new Date(r.created_at).toLocaleString('zh-CN'))}<span>${escape(labels[r.status])} · ${escape(labels[r.delivery]||r.delivery)}</span></button>`).join('') : '<p class="muted">还没有简报。</p>';
  $('history').querySelectorAll('button').forEach(b=>b.onclick=()=>showRun(b.dataset.id).catch(e=>notify(e.message)));
}
async function showRun(id) {
  clearTimeout(polling);currentRun=id;const uid=selected;
  const r=await api(`/users/${uid}/runs/${id}`);
  if (uid!==selected||currentRun!==id) return;
  const b=r.brief;
  $('reader').innerHTML=`<p class="meta">${escape(labels[r.status])} · ${escape(labels[r.delivery]||r.delivery)}</p>`+
    (r.error?`<p>${escape(r.error)}</p>`:'')+
    (b?`<h2 class="brief-title">${escape(b.title)}</h2><p class="brief-note">${escape(b.note)}</p><p class="meta">根据 RSS 摘要整理</p>`+
    b.items.map(i=>`<article class="article"><h3>${escape(i.title)}</h3><p>${escape(i.summary)}</p><p class="reason">入选理由：${escape(i.reason)}</p><p class="meta">${escape(i.source)} · ${escape(new Date(i.published_at).toLocaleString('zh-CN'))}</p><a href="${escape(i.url)}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></article>`).join('')+
    (!b.items.length?'<p class="muted">本次没有匹配的新闻。</p>':'')+
    (b.is_demo?'<p class="meta">模拟简报不可发送邮件。</p>':`<button id="send-mail" class="secondary" ${['sent','sending','unknown','failed'].includes(r.delivery)?'disabled':''}>发送这份简报</button>`):'<p class="muted">'+(r.status==='running'?'Agent 正在选择来源和整理材料…':'本次未生成简报。')+'</p>')+
    `<details><summary>工具调用记录 · ${r.tools.length} 次</summary><div>${r.tools.map(t=>`<div class="tool"><strong>${escape(t.name)}</strong> · ${t.duration.toFixed(2)} 秒<pre>参数：${escape(t.arguments)}\n结果：${escape(t.result)}</pre></div>`).join('')||'<p class="muted">暂无工具调用。</p>'}</div></details>`;
  if ($('send-mail')) $('send-mail').onclick=async()=>{const button=$('send-mail');button.disabled=true;try{const result=await api(`/users/${uid}/runs/${id}/send`,{method:'POST'});notify(labels[result.delivery]||result.delivery);await showRun(id);}catch(e){notify(e.message);button.disabled=false;}};
  await loadHistory();
  if (r.status==='running') polling=setTimeout(()=>showRun(id).catch(e=>notify(e.message)),2000);
}
$('users').onchange=e=>selectUser(e.target.value);
$('new-user').onclick=()=>selectUser('');
$('refresh').onclick=()=>loadHistory().catch(e=>notify(e.message));
$('profile').onsubmit=async e=>{
  e.preventDefault();const button=e.submitter;button.disabled=true;
  try {
    const profile={nickname:$('nickname').value.trim(),email:$('email').value.trim(),topics:split('topics'),keywords:split('keywords'),excluded_keywords:split('excluded'),send_time:$('time').value,enabled:$('enabled').checked};
    const result=await api(selected?`/users/${selected}`:'/users',{method:selected?'PUT':'POST',body:JSON.stringify(profile)});
    await loadUsers(); selectUser(result.id); notify('订阅已保存。');
  } catch(e) {notify(e.message);} finally {button.disabled=false;}
};
$('generate').onclick=async()=>{const uid=selected;$('generate').disabled=true;try{const r=await api(`/users/${uid}/runs`,{method:'POST'});if(uid===selected){notify('任务已开始，手动生成不会自动发送邮件。');await showRun(r.id);}}catch(e){notify(e.message);}finally{$('generate').disabled=!selected;}};
(async()=>{try{const h=await api('/health');$('health').textContent=`模型密钥${h.model_configured?'已提供':'未配置'} · 邮件${h.mail_configured?'已配置':'未配置'}`;await loadUsers();if(users.length)selectUser(users[0].id);}catch(e){notify(e.message);}})();
