"""Minimal practice UI served by the API (Phase 2 milestone:
practice screen against approved data, no build step)."""
from __future__ import annotations

PRACTICE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>11+ Practice</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem}
.card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
button{padding:.5rem 1rem;margin:.25rem;cursor:pointer}
.opt{display:block;width:100%;text-align:left}</style></head>
<body>
<h1>11+ Practice</h1>
<div><label>Student id <input id="sid" value="demo"></label>
<button onclick="start()">Start session</button></div>
<div id="q" class="card">Press Start.</div>
<div id="opts"></div>
<div id="fb" class="card" hidden></div>
<script>
let S={sid:'demo',sess:null,qs:[],i:0};
async function start(){
 S.sid=document.getElementById('sid').value||'demo';
 S.sess=(await (await fetch('/api/sessions?student_id='+encodeURIComponent(S.sid)+'&session_type=practice',{method:'POST'})).json()).session_id;
 S.qs=await (await fetch('/api/questions?limit=20')).json();
 S.i=0; show();
}
function show(){
 const q=S.qs[S.i]; if(!q){document.getElementById('q').textContent='Done.';document.getElementById('opts').innerHTML='';return;}
 const qhdr=document.getElementById('q'); qhdr.textContent='';
 const subj=document.createElement('b'); subj.textContent=(q.subject||'')+' / '+(q.topic||''); qhdr.appendChild(subj);
 const stem=document.createElement('p'); stem.textContent=q.question_text||''; qhdr.appendChild(stem);
 if(q.context){const ctx=document.createElement('p'); ctx.textContent=q.context; qhdr.insertBefore(ctx,stem);}
 const box=document.getElementById('opts'); box.innerHTML=''; document.getElementById('fb').hidden=true;
 (q.options||[]).forEach(o=>{const b=document.createElement('button');b.className='opt';b.textContent=o.letter+') '+o.text; b.onclick=()=>answer(q,o.letter); box.appendChild(b);});
}
async function answer(q,letter){
 const r=await (await fetch('/api/attempts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:S.sid,session_id:S.sess,question_id:q.id,chosen_answer:letter})})).json();
 const fb=document.getElementById('fb'); fb.hidden=false; fb.textContent='';
 const head=document.createElement('b');
 head.textContent=r.is_correct?'Correct. ':'Not quite. ';
 fb.appendChild(head);
 const exp=document.createElement('span'); exp.textContent=r.explanation||'';
 fb.appendChild(exp);
 const br=document.createElement('br'); fb.appendChild(br);
 const b=document.createElement('button'); b.textContent='Next'; b.onclick=next;
 fb.appendChild(b);
}
function next(){S.i++;show();}
</script></body></html>"""
