"""Full dashboard pages: Home, Learn, Mock Exams, Progress, Parent.
Served by the API with no build step; all data from approved-only
and deterministic aggregation endpoints.
"""
from __future__ import annotations

def _page(title: str, body: str) -> str:
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>" + title + " - 11+ Platform</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:0 1rem 3rem}"
            "nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}"
            "nav a{padding:.4rem .8rem;border:1px solid #ccc;border-radius:6px;text-decoration:none;color:#111}"
            ".card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:.75rem 0}"
            "button{padding:.5rem 1rem;margin:.25rem;cursor:pointer}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.4rem;text-align:left}"
            ".muted{color:#555}</style></head><body>"
            "<nav><a href=\"/\">Home</a><a href=\"/learn\">Learn</a><a href=\"/practice\">Practice</a>"
            "<a href=\"/mocks\">Mock Exams</a><a href=\"/progress\">Progress</a><a href=\"/parent\">Parent</a></nav>"
            + body + "</body></html>")

HOME = _page("Home", """<h1>11+ Preparation Platform</h1>
<p class="muted">Learn a topic, try a worked example, practise, review mistakes, re-test.</p>
<div class="card"><b>Learn</b><p>Lessons, strategies, worked examples and common mistakes per topic.</p><a href="/learn">Open Learn</a></div>
<div class="card"><b>Practice</b><p>Approved questions only. <a href="/practice">Open Practice</a></p></div>
<div class="card"><b>Mock Exams</b><p>Authentic source-paper mode or generated papers. <a href="/mocks">Open Mocks</a></p></div>
<div class="card"><b>Progress + Parent</b><p><a href="/progress">Progress</a> - <a href="/parent">Parent dashboard</a></p></div>""")

LEARN = _page("Learn", """<h1>Learn</h1>
<div><label>Topic id <input id="t" value="maths-fractions" size="24"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){
const t=document.getElementById('t').value;
const c=await (await fetch('/api/curriculum/'+encodeURIComponent(t))).json();
const sec=(h,items,k)=>'<h3>'+h+'</h3>'+(items.map(i=>'<div class=card><b>'+i.title+'</b><pre style=white-space:pre-wrap>'+(i.content||i.explanation||'')+'</pre></div>').join('')||'<p class=muted>None yet.</p>');
document.getElementById('out').innerHTML=sec('Lessons',c.lessons)+sec('Strategies',c.strategies)+sec('Worked examples',c.worked_examples)+'<h3>Common mistakes</h3>'+(c.common_mistakes.map(m=>'<div class=card><b>'+m.mistake+'</b><pre style=white-space:pre-wrap>'+m.explanation+'</pre></div>').join('')||'<p class=muted>None yet.</p>');}
load();</script>""")

MOCKS = _page("Mock Exams", """<h1>Mock Exams</h1>
<div class="card"><h3>Build a generated paper (approved questions only)</h3>
<label>Name <input id="n" value="Practice paper"></label><br>
<label>Subject <input id="s" value="maths"></label>
<label>Count <input id="c" value="10" size="4"></label>
<label>Minutes <input id="m" value="30" size="4"></label><br>
<button onclick="build()">Assemble</button><div id="out"></div></div>
<script>
const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
function showErr(msg){const o=document.getElementById('out');o.innerHTML='<p style="color:#a00">'+esc(msg)+'</p>';}
async function build(){
 const out=document.getElementById('out'); out.innerHTML='<p class="muted">Building…</p>';
 const count=parseInt(document.getElementById('c').value,10)||10;
 const minutes=parseInt(document.getElementById('m').value,10)||30;
 const subject=document.getElementById('s').value.trim();
 const name=document.getElementById('n').value.trim()||'Practice paper';
 // POST /api/exams returns {exam_id}.
 let e;
 try{ e=await (await fetch('/api/exams',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})).json(); }
 catch(err){ return showErr('Could not create the exam (network error).'); }
 if(!e||!e.exam_id){ return showErr('Could not create the exam.'); }
 // AssembleIn requires {mode, sections:[{name,subject,topic,difficulty,count,time_minutes,instructions,section_number}], document_id, seed}.
 const body={mode:'generated',seed:42,sections:[{name:name,subject:subject,count:count,time_minutes:minutes,section_number:1}]};
 let r;
 try{ r=await (await fetch('/api/exams/'+encodeURIComponent(e.exam_id)+'/assemble',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json(); }
 catch(err){ return showErr('Could not assemble the exam (network error).'); }
 // assemble_generated returns {sections:int, questions:[ids]}.
 if(r&&Array.isArray(r.questions)){
   out.innerHTML='<p style="color:#080">Assembled '+r.questions.length+' question(s) across '+r.sections+' section(s) for exam '+esc(e.exam_id)+'.</p>';
 } else {
   out.innerHTML='<p style="color:#a00">Assembly returned no questions. There may be no approved questions for this subject yet.</p>';
 }
}
</script>""")


PROGRESS = _page("Progress", """<h1>Progress</h1>
<div class="card"><label>View progress for <input id="stu" style="width:180px" value="s1"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>
const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const pct=v=>Math.round((v||0)*100)+'%';
async function load(){
 const stu=document.getElementById('stu').value.trim();
 const out=document.getElementById('out'); out.innerHTML='<p class="muted">Loading…</p>';
 // GET /api/progress/{id} returns {student_id, weak_topics:[{topic,accuracy,practiced}],
 // weak_skills:[{skill,topic,accuracy,practiced}], review:{total,by_state,due_now,upcoming,...},
 // recommendations:[...]}. Render only fields the API actually returns.
 let d;
 try{ d=await (await fetch('/api/progress/'+encodeURIComponent(stu))).json(); }
 catch(err){ return out.innerHTML='<p style="color:#a00">Could not load progress (network error).</p>'; }
 if(!d||typeof d!=='object'||d.detail){ return out.innerHTML='<p style="color:#a00">Could not load progress for '+esc(stu)+'.</p>'; }
 const rv=d.review||{};
 let h='<p>Progress for '+esc(d.student_id||stu)+': '+esc(rv.total||0)+' review item(s), '
   +esc(rv.due_now||0)+' due now, '+esc(rv.upcoming||0)+' upcoming.</p>';
 const topics=d.weak_topics||[];
 h+='<h3>Weak topics</h3>'+(topics.length?'<table><tr><th>Topic</th><th>Accuracy</th><th>Practiced</th></tr>'
    +topics.map(t=>'<tr><td>'+esc(t.topic)+'</td><td>'+esc(pct(t.accuracy))+'</td><td>'+esc(t.practiced)+'</td></tr>').join('')+'</table>'
    :'<p class="muted">No weak topics identified yet.</p>');
 const skills=d.weak_skills||[];
 h+='<h3>Weak skills</h3>'+(skills.length?'<ul>'+skills.map(s=>'<li>'+esc(s.skill)+' ('+esc(s.topic)+') — '+esc(pct(s.accuracy))+'</li>').join('')+'</ul>'
    :'<p class="muted">No weak skills identified yet.</p>');
 out.innerHTML=h;
}
load();</script>""")

PARENT = _page("Parent", """<h1>Parent dashboard</h1>
<div class="card"><label>Student <input id="stu" style="width:180px" value="s1"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>
const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
async function load(){
 const stu=document.getElementById('stu').value.trim();
 const out=document.getElementById('out'); out.innerHTML='<p class="muted">Loading…</p>';
 let d;
 try{ d=await (await fetch('/api/parent/'+encodeURIComponent(stu))).json(); }
 catch(err){ return out.innerHTML='<p style="color:#a00">Could not load the parent summary (network error).</p>'; }
 if(!d||typeof d!=='object'){ return out.innerHTML='<p style="color:#a00">Unexpected response from the server.</p>'; }
 const pct=v=>Math.round((v||0)*100)+'%';
 let h='<p>Progress for '+esc(stu)+': '+esc(d.questions_answered||0)+' question(s) answered, '
      +esc(d.practice_completed||0)+' practice attempt(s), '+esc(d.practice_hours||0)+' h practised.</p>';
 // subject performance: {subject:{attempted,correct,accuracy}}
 const subs=Object.keys(d.subject_performance||{});
 h+='<h3>Subject performance</h3>'+(subs.length?'<table><tr><th>Subject</th><th>Accuracy</th><th>Correct</th><th>Attempted</th></tr>'
    +subs.map(s=>{const r=d.subject_performance[s];return '<tr><td>'+esc(s)+'</td><td>'+esc(pct(r.accuracy))+'</td><td>'+esc(r.correct)+'</td><td>'+esc(r.attempted)+'</td></tr>';}).join('')+'</table>'
    :'<p class="muted">No subject activity yet.</p>');
 // weak areas: [{topic,accuracy,practiced}]
 const weak=d.weak_areas||[];
 h+='<h3>Weak areas</h3>'+(weak.length?'<ul>'+weak.map(w=>'<li>'+esc(w.topic)+' — '+esc(pct(w.accuracy))+' ('+esc(w.practiced)+' practised)</li>').join('')+'</ul>':'<p class="muted">No weak areas identified yet.</p>');
 out.innerHTML=h;
}
load();</script>""")

REVIEW = _page("Review", """<h1>Question review</h1>
<div id=errors style="display:none;color:#a00;"></div>
<p class="muted">Server-side token required for changes. Set <code>PLUS_REVIEWER_TOKEN</code>
and paste it below. Approval is blocked until every requirement is met.</p>
<label>Reviewer token <input id="tok" type="password" placeholder="token"></label>
<button onclick="loadQueue()">Load queue</button>
<div id="queue"></div><div id="detail"></div>
<script>
 function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
 // Shared request helper. ALWAYS returns {ok:boolean,status:number,data:*,net:boolean};
 // `data` is already-parsed JSON (or {} on parse failure) and `net` is true when
 // fetch itself threw (offline/DNS/CORS). Callers use this contract and must NOT
 // call .json() on the result. No tokens, stack traces or internal paths are
 // surfaced -- only status + a safe message.
 const api=async(u,o)=>{const h={'Content-Type':'application/json'};
 const t=document.getElementById('tok').value;if(t)h['X-Reviewer-Token']=t;
 try{
   const r=await fetch(u,{method:o?'POST':'GET',headers:h,body:o?JSON.stringify(o):undefined});
   const data=await r.json().catch(()=>({}));
   return {ok:r.ok,status:r.status,data:data,net:false};
 }catch(e){return {ok:false,status:0,data:{},net:true};}};
 // Safe, token-free error text from an api() result.
 function errText(r){
   if(r.net)return 'Network error: could not reach the server.';
   const d=r.data&&r.data.detail?String(r.data.detail):'';
   return 'Request failed ('+(r.status||'?')+')'+(d?': '+d:'');
 }
 let errorMsg='';
 function showError(msg){errorMsg=msg||'';
   const el=document.getElementById('errors');if(el){el.textContent=errorMsg;el.style.display=errorMsg?'':'none';}}
 // Single-flight guard so a slow request cannot be double-submitted.
 let busy=false;
 async function mustOk(r,what){if(!r.ok){showError(what+': '+errText(r));return false;}return true;}
 async function loadQueue(){
   if(busy)return;busy=true;
   try{
     const r=await api('/api/review-queue?limit=50');
     showError('');
     const box=document.getElementById('queue');
     if(!r.ok){showError('Load queue: '+errText(r));return;}
     box.innerHTML=Array.isArray(r.data)&&r.data.length?
       '<table><tr><th>Subject/topic</th><th>Status</th><th></th></tr>'+
       r.data.map(function(q){return '<tr><td>'+esc(q.subject)+'/'+esc(q.topic)+'</td><td>'+esc(q.status)+'</td><td><button onclick="loadDetail('+JSON.stringify(q.id)+')">Open</button></td></tr>';}).join('')+'</table>'
      :'<p class="muted">No candidates awaiting review.</p>';
   }finally{busy=false;}}
 async function loadDetail(id){
   const r=await api('/api/review/'+id);
   if(!r.ok){showError('Load question: '+errText(r));return;}
   showError('');
   const d=r.data||{};
   const blockers=(d.approval_blockers||[]).map(function(b){return '<li>'+esc(b)+'</li>';}).join('');
   const opts=(d.options||[]).map(function(o){return '<li>'+esc(o.letter||o.label||'')+'. '+(o.text?esc(o.text):'')+'</li>';}).join('');
   const prov=(d.provenance||[]).map(function(p){return esc(p.filename)+' p.'+esc(p.page_number)+' #'+esc(p.question_number);}).join('; ');
   const excerpt=d.source_excerpt?'<pre style="white-space:pre-wrap">'+esc(d.source_excerpt)+'</pre>':'';
   document.getElementById('detail').innerHTML=
     '<div class="card"><b>'+esc(d.question_text||'')+'</b>'+
     '<p class="muted">Type: '+esc(d.question_type||'')+' | Review: '+esc(d.review_status||'')+
     ' | Answer: '+esc(d.answer_status||'')+' | Explanation: '+esc(d.explanation_status||'')+'</p>'+
     '<p class="muted">Source: '+(prov||'none')+'</p>'+excerpt+'<ul>'+opts+'</ul>'+
     '<p><b>Answer:</b> '+esc(d.correct_answer||'')+' <b>Explanation:</b> '+esc(d.explanation||'---')+'</p>'+
     (blockers?'<p style="color:#a00;"><b>Blocked:</b><ul>'+blockers+'</ul></p>'
      :'<p style="color:#080;"><b>Eligible to approve.</b></p>')+
     '<div class="card"><label>Question text <textarea id="qt" rows="3">'+esc(d.question_text||'')+'</textarea></label></div>'+
     '<div class="card">Answer <input id="ca" size="40" value="'+esc(d.correct_answer||'')+'"></div>'+
     '<div class="card">Options <textarea id="opts" rows="5">'+esc(JSON.stringify(d.options||[]))+'</textarea></div>'+
     '<div class="card"><label>Explanation <textarea id="ex" rows="3">'+esc(d.explanation||'')+'</textarea></label></div><div class="card"><label>Answer evidence (source ref) <input id="ev" size="40" value="'+esc(d.answer_evidence||'')+'"></label></div>'+
     '<div class="card"><button onclick="verifyA('+JSON.stringify(id)+')">Verify answer</button> '+
     '<button onclick="verifyE('+JSON.stringify(id)+')">Verify explanation</button></div>'+
     '<div class="card"><button onclick="editQ('+JSON.stringify(id)+')">Save edit</button></div>'+
     '<div class="card"><button onclick="decide('+JSON.stringify(id)+',&quot;approved&quot;)">Approved</button> '+
     '<button onclick="decide('+JSON.stringify(id)+',&quot;rejected&quot;)">Rejected</button></div></div>';}
 async function verifyA(id){if(busy)return;busy=true;
 try{const r=await api('/api/review/'+id+'/verify-answer',
 {evidence:document.getElementById('ev').value});if(mustOk(r,'Verify answer'))loadDetail(id);}
 finally{busy=false;}}
 async function verifyE(id){if(busy)return;busy=true;
 try{const r=await api('/api/review/'+id+'/verify-explanation',
 {evidence:document.getElementById('ev').value});if(mustOk(r,'Verify explanation'))loadDetail(id);}
 finally{busy=false;}}
 async function editQ(id){if(busy)return;busy=true;
 try{
   let opts;try{opts=JSON.parse(document.getElementById('opts').value);}
   catch(e){showError('Options must be valid JSON (e.g. [{"letter":"A","text":"..."},...]).');return;}
   const r=await api('/api/review/'+id+'/edit',
   {question_text:document.getElementById('qt').value,
   correct_answer:document.getElementById('ca').value,explanation:document.getElementById('ex').value,
   options_json:opts});
   if(mustOk(r,'Save edit')){showError('');loadDetail(id);}
 }finally{busy=false;}}
 async function decide(id,action){if(busy)return;busy=true;
 try{const r=await api('/api/review/'+id,{status:action});if(mustOk(r,'Decision')){showError('');loadDetail(id);}}
 finally{busy=false;}}
""")
