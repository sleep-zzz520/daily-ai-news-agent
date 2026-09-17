// Exercise actual frontend state helpers without network, credentials or mail.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
function element(id) {
  if (!nodes.has(id)) nodes.set(id, {value:'',checked:false,hidden:false,open:false,scrollTop:0,
    textContent:'',innerHTML:'',dataset:{},classList:{toggle(){}},addEventListener(){},querySelectorAll(){return [];},
    showModal(){this.open=true;},close(){this.open=false;}});
  return nodes.get(id);
}
element('time').value='09:00';
const memory = new Map();
const context = vm.createContext({document:{getElementById:element,querySelectorAll:()=>[]},
  localStorage:{getItem:key=>memory.get(key),setItem:(key,value)=>memory.set(key,value)},
  fetch:()=>new Promise(()=>{}),setTimeout,clearTimeout,console});
vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
const evaluate = code => vm.runInContext(code,context);
evaluate(`users=[{id:'u',nickname:'测试',email:'test@example.com',topics:['AI Agent'],keywords:[],excluded_keywords:[],send_time:'09:00',enabled:false}];selected='u';populate();`);
assert.equal(evaluate('dirty()'),false);
assert.equal(element('save-profile').disabled,true);
assert.equal(element('schedule-fields').hidden,true);
element('enabled').checked=true;
evaluate('updateDirty()');
assert.equal(element('schedule-fields').hidden,false);
assert.equal(element('time').disabled,false);
assert.equal(element('save-profile').disabled,false);
evaluate('saving=true;updateSaveState()');
assert.equal(element('save-profile').disabled,true);
assert.equal(element('save-state').textContent,'保存中…');
evaluate('saving=false;populate()');
element('keywords').value='尚未保存';
assert.equal(evaluate('requireSaved()'),false);
assert.equal(element('settings-panel').open,true);
assert.match(element('form-message').textContent,/未保存/);
evaluate('populate()');
assert.equal(evaluate('requireSaved()'),true);
assert.match(element('subscription-summary').textContent,/每日推送已暂停/);
assert.match(evaluate(`deliveryHTML({delivery:'not_sent',brief:{}})`),/test@example.com/);
assert.match(evaluate(`deliveryHTML({delivery:'sent',brief:{}})`),/已发送/);
assert.doesNotMatch(evaluate(`deliveryHTML({delivery:'sent',brief:{}})`),/id="send-mail"/);
assert.match(evaluate(`deliveryHTML({delivery:'unknown',brief:{}})`),/避免重复发送/);
assert.match(evaluate(`deliveryHTML({delivery:'failed',brief:{},delivery_detail:{error:'SMTP 550'}})`),/SMTP 550/);
assert.doesNotMatch(evaluate(`deliveryHTML({delivery:'not_sent',brief:{is_demo:true}})`),/id="send-mail"/);
evaluate(`renderRun({status:'completed',created_at:'2026-09-17T03:30:00Z',delivery:'sent',tools:[],brief:{title:'错误标题 2020-01-01',note:'<script>bad</script>',items:[]}});`);
assert.doesNotMatch(element('reader').innerHTML,/2020-01-01/);
assert.match(element('reader').innerHTML,/2026\/9\/17/);
assert.match(element('reader').innerHTML,/&lt;script&gt;/);
assert.equal(evaluate(`summaryPoints('第一点。第二点！尾句').join('')`),'第一点。第二点！尾句');
assert.equal(evaluate(`summaryPoints('一。二。三。四。五。').length`),4);
assert.equal(evaluate(`summaryPoints('一。二。三。四。五。').join('')`),'一。二。三。四。五。');
assert.equal(evaluate(`summaryPoints('GLM 4.7 supports agents.').length`),1);
evaluate(`renderRun({status:'completed',created_at:'2026-09-17T03:30:00Z',delivery:'sent',tools:[],brief:{note:'采集说明测试',items:[{title:'新闻重点',summary:'第一点。第二点。',source:'测试来源',published_at:'2026-09-17T01:00:00Z',url:'https://example.com',reason:'匹配关注话题'}]}});`);
const readingHTML=element('reader').innerHTML;
assert.ok(readingHTML.indexOf('新闻重点')<readingHTML.indexOf('采集说明测试'));
assert.match(readingHTML,/class="takeaways"/);
assert.match(readingHTML,/class="article-facts"/);
assert.match(readingHTML,/data-detail="reason-0"/);
assert.match(readingHTML,/data-detail="collection"/);
assert.doesNotMatch(readingHTML,/<details[^>]*\sopen(?:\s|>)/);
evaluate(`currentRun='remembered';storage('user','u');storage('run:u',currentRun);`);
element('content').scrollTop=480;
evaluate('saveReadingPosition()');
assert.equal(memory.get('scroll:remembered'),'480');
assert.equal(memory.get('run:u'),'remembered');
console.log('Frontend checks passed: unsaved guards, delivery states, dates, escaping, reading persistence and editorial hierarchy.');
