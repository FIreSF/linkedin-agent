"""Local web UI for lk. Binds to 127.0.0.1 only; no external requests."""

import base64
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import comments, config, posts, publish, queue as queue_mod, safety, store, voice, watch as watch_mod

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>lk</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#252a34;--text:#e6e9ef;--dim:#8b93a7;
--accent:#4f8cff;--ok:#33c27f;--warn:#e2b341;--bad:#e2564f}
*{box-sizing:border-box}
body{margin:0;display:flex;height:100vh;background:var(--bg);color:var(--text);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
aside{width:300px;border-right:1px solid var(--line);display:flex;flex-direction:column;background:var(--panel)}
aside header{padding:14px 16px;border-bottom:1px solid var(--line);font-weight:600;letter-spacing:.5px}
aside header small{display:block;color:var(--dim);font-weight:400;font-size:11px;margin-top:2px}
#list{flex:1;overflow:auto}
.item{padding:10px 16px;border-bottom:1px solid var(--line);cursor:pointer;font-size:13px}
.item:hover{background:#1d2229}
.item.active{background:#22304a;border-left:2px solid var(--accent)}
.item .t{color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .m{color:var(--dim);font-size:11px;margin-top:2px}
aside footer{padding:10px 16px;border-top:1px solid var(--line);font-size:11px;color:var(--dim)}
main{flex:1;overflow:auto;padding:24px 28px}
h2{margin:0 0 16px;font-size:16px}
label{display:block;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin:12px 0 4px}
input,textarea,select{width:100%;background:#0d0f13;border:1px solid var(--line);color:var(--text);
border-radius:6px;padding:9px 11px;font:inherit;outline:none}
input:focus,textarea:focus{border-color:var(--accent)}
textarea{min-height:280px;resize:vertical;line-height:1.6}
button{background:#232936;color:var(--text);border:1px solid var(--line);border-radius:6px;
padding:8px 14px;font:inherit;cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
button.ghost{background:transparent}
button:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}
.meta{color:var(--dim);font-size:12px;margin-bottom:12px;display:flex;gap:14px;flex-wrap:wrap}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;border:1px solid var(--line)}
.pill.draft{color:var(--warn)}.pill.posted{color:var(--ok)}.pill.rejected{color:var(--bad)}
.findings{margin-top:16px;font-size:13px}
.findings div{padding:6px 0;border-bottom:1px solid var(--line)}
.lvl{font-weight:600;margin-right:8px}
.HIGH{color:var(--bad)}.MEDIUM{color:var(--warn)}.LOW{color:var(--dim)}
.score{font-size:28px;font-weight:700;margin:8px 0}
.beat{display:grid;grid-template-columns:18px 90px 1fr;gap:8px;padding:5px 0;font-size:13px}
.beat .q{color:var(--dim);font-style:italic;font-size:12px}
code{background:#0d0f13;padding:2px 6px;border-radius:4px;font-size:12px}
#toast{position:fixed;bottom:20px;right:20px;background:#232936;border:1px solid var(--line);
padding:12px 16px;border-radius:8px;max-width:420px;display:none;font-size:13px}
#toast.err{border-color:var(--bad)}
.spin{display:inline-block;width:12px;height:12px;border:2px solid #555;border-top-color:var(--accent);
border-radius:50%;animation:s .8s linear infinite;vertical-align:-1px;margin-right:8px}
@keyframes s{to{transform:rotate(360deg)}}
.hidden{display:none!important}
</style></head><body>
<aside>
  <header>lk<small id="stat">loading…</small></header>
  <div id="list"></div>
  <footer>
    <button class="primary" style="width:100%" onclick="newDraft()">+ New draft</button>
    <button style="width:100%;margin-top:6px" onclick="showQueue()">Pending replies <span id="qbadge"></span></button>
  </footer>
</aside>
<main>
  <div id="empty"><h2>Nothing selected</h2>
    <p style="color:var(--dim)">Pick a draft on the left, or create a new one.</p></div>

  <div id="queueView" class="hidden">
    <h2>Pending replies</h2>
    <p style="color:var(--dim)">Nothing sends until you approve. One reply per person per post.</p>
    <p style="color:var(--dim)" id="qlimits"></p>
    <div class="row" style="margin-top:10px">
      <button onclick="checkInbox()">Check for new comments</button>
    </div>

    <h2 style="margin-top:26px">Reply to a comment</h2>
    <p style="color:var(--dim)">Paste the comment. The agent drafts it; you approve it before it sends.</p>
    <div class="grid" style="margin-top:10px">
      <div><label>Their comment</label><textarea id="rComment" style="min-height:70px" placeholder="paste the comment text"></textarea></div>
      <div><label>Their name</label><input id="rAuthor" placeholder="Sara"></div>
      <div><label>Post URL</label><input id="rUrl" placeholder="https://www.linkedin.com/feed/update/urn:li:activity:..."></div>
      <div><label>Your post text (optional, for context)</label><textarea id="rPost" style="min-height:60px" placeholder="paste your post if you want a more specific reply"></textarea></div>
    </div>
    <div class="row" style="margin-top:10px">
      <button class="primary" id="replyBtn" onclick="draftReply()">Draft reply</button>
    </div>

    <div id="queueList" style="margin-top:18px"></div>
  </div>

  <div id="new" class="hidden">
    <h2>New draft</h2>
    <label>Type</label>
    <select id="kind" onchange="toggleKind()">
      <option value="post">Post about a topic</option>
      <option value="cert">Certificate / badge story</option>
    </select>
    <div id="certFields" class="grid hidden">
      <div><label>Certificate</label><input id="title" placeholder="CompTIA Security+"></div>
      <div><label>Issuer</label><input id="issuer" placeholder="CompTIA"></div>
      <div><label>Skills</label><input id="skills" placeholder="threat analysis, IR"></div>
      <div><label>Tone</label><input id="tone" placeholder="dry, no emoji"></div>
    </div>
    <div id="postFields"><label id="topicLabel">Topic</label><input id="topic" placeholder="why I stopped collecting certificates"></div>
    <label>Story / angle (what really happened)</label>
    <textarea id="story" style="min-height:90px" placeholder="Failed the first attempt. Second time I built a home lab instead of re-watching the course."></textarea>
    <div class="row"><button class="primary" id="genBtn" onclick="generate()">Generate</button></div>
  </div>

  <div id="detail" class="hidden">
    <h2 id="dtitle"></h2>
    <div class="meta" id="dmeta"></div>
    <textarea id="dtext"></textarea>

    <label>Image (optional)</label>
    <div class="row" style="margin-top:6px">
      <input type="file" id="imgFile" accept="image/png,image/jpeg,image/gif" style="max-width:260px" onchange="uploadImage()">
      <input id="imgAlt" placeholder="Alt text: what the image shows" style="max-width:330px" onchange="saveAlt()">
      <button class="ghost" onclick="removeImage()">Remove</button>
    </div>
    <div id="imgPreview" style="margin-top:10px"></div>

    <div class="row">
      <button class="primary" onclick="saveText()">Save edit</button>
      <button onclick="coach()">Coach</button>
      <button onclick="humanizeDraft()">Humanize</button>
      <button onclick="copyText()">Copy</button>
      <button onclick="mark('posted')">Mark posted</button>
      <button onclick="dryRun()">Dry run</button>
      <button class="primary" onclick="publishNow()">Publish</button>
    </div>
    <div class="findings" id="findings"></div>
    <div id="coachout"></div>
  </div>
</main>
<div id="toast"></div>

<script>
let current=null, busy=false;
const $=id=>document.getElementById(id);
const api=async(p,body)=>{
  const r=await fetch(p,{method:body?'POST':'GET',
    headers:body?{'Content-Type':'application/json'}:{},
    body:body?JSON.stringify(body):undefined});
  const j=await r.json().catch(()=>({error:'bad response'}));
  if(!r.ok||j.error) throw new Error(j.error||r.statusText);
  return j;
};
const toast=(m,err)=>{const t=$('toast');t.textContent=m;t.className=err?'err':'';
  t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',err?7000:3000)};
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function boot(){
  try{const s=await api('/api/state');
    $('stat').textContent=`${s.name||'not connected'} · ${s.model} · ${s.examples} examples`;
    if(!s.connected) $('stat').textContent+=` · ⚠ no token`;
  }catch(e){}
  loadDrafts(); refreshQueueBadge();
}
async function refreshQueueBadge(){
  try{const r=await api('/api/queue');
    $('qbadge').textContent=r.pending.length?`(${r.pending.length})`:'';
  }catch(e){}
}
async function showQueue(){
  current=null;['new','detail','empty'].forEach(i=>$(i).classList.add('hidden'));
  $('queueView').classList.remove('hidden');
  await renderQueue(); loadDrafts();
}
async function renderQueue(){
  const r=await api('/api/queue');
  $('qlimits').textContent=`Today: ${r.used_today}/${r.cap} replies used`
    + (r.quiet?' · quiet hours, sends will wait':'');
  if(!r.pending.length){
    $('queueList').innerHTML='<div style="color:var(--dim)">Nothing waiting for approval.</div>';
  } else {
    $('queueList').innerHTML=r.pending.map(i=>`
      <div class="item" style="cursor:default;margin-bottom:10px">
        <div class="t">${esc(i.label||'reply')} <span class="pill">${i.status}</span></div>
        <div style="white-space:pre-wrap;margin:8px 0;font-size:13px">${esc(i.text)}</div>
        <div class="m" style="margin-bottom:8px">due ${new Date(i.due*1000).toLocaleTimeString()}
          ${i.author?'· to '+esc(i.author):''}</div>
        <div class="row">
          <button class="primary" onclick="approveItem('${i.id}')">Approve</button>
          <button class="ghost" onclick="rejectItem('${i.id}')">Reject</button>
        </div>
      </div>`).join('');
  }
  refreshQueueBadge();
}
async function approveItem(id){
  try{await api('/api/queue/approve',{id});toast('Approved');await renderQueue()}
  catch(e){toast(e.message,true)}
}
async function rejectItem(id){
  try{await api('/api/queue/reject',{id});toast('Rejected');await renderQueue()}
  catch(e){toast(e.message,true)}
}
async function checkInbox(){
  toast('Checking LinkedIn for new comments…');
  try{const r=await api('/api/inbox/check',{});
    if(r.error){toast(r.error,true);return}
    toast(`Checked ${r.posts} posts · ${r.new_comments} new · ${r.drafted} drafted`);
    await renderQueue();
  }catch(e){toast(e.message,true)}
}
async function draftReply(){
  const comment=$('rComment').value.trim(), author=$('rAuthor').value.trim();
  const url=$('rUrl').value.trim(), post=$('rPost').value.trim();
  if(!comment) return toast('Paste the comment first',true);
  if(!url) return toast('Post URL is required (that is where the reply goes)',true);
  const b=$('replyBtn');b.disabled=true;b.innerHTML='<span class="spin"></span>Drafting';
  try{const r=await api('/api/reply',{comment,author,url,post});
    toast(r.warnings&&r.warnings.length?r.warnings[0]:'Drafted — approve it below', !!(r.warnings&&r.warnings.length));
    $('rComment').value='';$('rPost').value='';
    await renderQueue();
  }catch(e){toast(e.message,true)}
  finally{b.disabled=false;b.textContent='Draft reply'}
}
async function loadDrafts(){
  const rows=await api('/api/drafts');
  $('list').innerHTML=rows.map(r=>`<div class="item ${r.id===current?'active':''}" onclick="openDraft('${r.id}')">
    <div class="t">${esc(r.title||r.kind)}</div>
    <div class="m"><span class="pill ${r.status}">${r.status}</span> ${r.kind} · ${r.chars}c</div></div>`).join('')
    || '<div class="item" style="color:var(--dim)">No drafts yet</div>';
}
function newDraft(){$('new').classList.remove('hidden');$('detail').classList.add('hidden');
  $('queueView').classList.add('hidden');$('empty').classList.add('hidden');current=null;loadDrafts()}
function toggleKind(){const c=$('kind').value==='cert';
  $('certFields').classList.toggle('hidden',!c);$('postFields').classList.toggle('hidden',c);
  $('topicLabel').textContent='Topic'}
async function generate(){
  const kind=$('kind').value;
  const body=kind==='cert'
    ? {kind,title:$('title').value,issuer:$('issuer').value,skills:$('skills').value,
       story:$('story').value,tone:$('tone').value}
    : {kind,topic:$('topic').value,angle:$('story').value};
  if(kind==='cert'&&!body.title) return toast('Certificate name required',true);
  if(kind==='post'&&!body.topic) return toast('Topic required',true);
  const b=$('genBtn');b.disabled=true;b.innerHTML='<span class="spin"></span>Generating (1-3 min)';
  try{const r=await api('/api/generate',body);toast('Draft created');
    await loadDrafts();openDraft(r.id)}
  catch(e){toast(e.message,true)}
  finally{b.disabled=false;b.textContent='Generate'}
}
async function openDraft(id){
  current=id;$('new').classList.add('hidden');$('empty').classList.add('hidden');
  $('queueView').classList.add('hidden');
  $('detail').classList.remove('hidden');$('coachout').innerHTML='';
  const d=await api('/api/draft/'+id);
  $('dtitle').textContent=d.record.title||d.record.kind;
  $('dmeta').innerHTML=`<span class="pill ${d.record.status}">${d.record.status}</span>
    <span>${d.record.kind}</span><span>${d.record.chars} chars</span><span>${d.record.created}</span>`;
  $('dtext').value=d.record.text;
  $('imgAlt').value=(d.record.image&&d.record.image.alt)||'';
  renderImage(d.record);
  $('findings').innerHTML=d.findings.length
    ? d.findings.map(f=>`<div><span class="lvl ${f.level}">${f.level}</span>${esc(f.message)}</div>`).join('')
    : '<div style="color:var(--ok)">No spam signals found. Safe to post.</div>';
  loadDrafts();
}
function renderImage(rec){
  const img=rec.image;
  if(!img||!img.path){$('imgPreview').innerHTML='';return}
  const url='/api/draft/'+encodeURIComponent(rec.id)+'/image?t='+Date.now();
  $('imgPreview').innerHTML=`<img src="${url}" alt="${esc(img.alt||'')}"
    style="max-width:340px;max-height:240px;border:1px solid var(--line);border-radius:6px;display:block">
    <div style="color:var(--dim);font-size:11px;margin-top:5px">${esc(img.path.split('/').pop())}</div>`;
}
async function uploadImage(){
  if(!current)return;
  const f=$('imgFile').files[0]; if(!f)return;
  if(f.size>10*1024*1024) return toast('Image must be under 10 MB',true);
  const b64=await new Promise((res,rej)=>{const r=new FileReader();
    r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f)});
  try{await api('/api/draft/'+current+'/image',{name:f.name,data:b64,alt:$('imgAlt').value});
    toast('Image attached');await openDraft(current)}
  catch(e){toast(e.message,true)}
}
async function saveAlt(){
  if(!current)return;
  try{await api('/api/draft/'+current+'/image-alt',{alt:$('imgAlt').value})}
  catch(e){toast(e.message,true)}
}
async function removeImage(){
  if(!current)return;
  try{await api('/api/draft/'+current+'/image-remove',{});toast('Image removed');await openDraft(current)}
  catch(e){toast(e.message,true)}
}
async function saveText(){
  if(!current)return;
  try{await api('/api/draft/'+current+'/text',{text:$('dtext').value});
    toast('Saved');const d=await api('/api/draft/'+current);$('dmeta').innerHTML=
    `<span class="pill ${d.record.status}">${d.record.status}</span><span>${d.record.kind}</span>
     <span>${d.record.chars} chars</span>`;$('findings').innerHTML=d.findings.length
    ? d.findings.map(f=>`<div><span class="lvl ${f.level}">${f.level}</span>${esc(f.message)}</div>`).join('')
    : '<div style="color:var(--ok)">No spam signals found. Safe to post.</div>';loadDrafts()}
  catch(e){toast(e.message,true)}
}
async function humanizeDraft(){
  if(!current)return;
  try{await saveText();
    const r=await api('/api/draft/'+current+'/humanize',{});
    if(!r.changes.length){toast('Already clean');return}
    toast(`${r.changes.length} fix(es) applied`);
    await openDraft(current);
  }catch(e){toast(e.message,true)}
}
async function coach(){
  if(!current)return;
  $('coachout').innerHTML='<p style="color:var(--dim)"><span class="spin"></span>Scoring (1-3 min)…</p>';
  try{await saveText();const r=await api('/api/draft/'+current+'/coach');
    const beats=['hook','stakes','turn','proof','invite'].map(b=>{
      const x=r.beats[b];
      return `<div class="beat"><span>${x.ok?'✓':'✕'}</span><span>${b}</span>
        <span>${esc(x.note)}${!x.ok&&x.quote?`<div class="q">“${esc(x.quote)}”</div>`:''}</span></div>`;
    }).join('');
    $('coachout').innerHTML=`<div class="score">${r.score}/10</div>${beats}
      <h2 style="margin-top:18px">Fix</h2>${r.fixes.map((f,i)=>`<div>${i+1}. ${esc(f)}</div>`).join('')}
      ${r.rewrite?`<h2 style="margin-top:18px">Rewrite</h2><pre style="white-space:pre-wrap;color:var(--dim)">${esc(r.rewrite)}</pre>`:''}`}
  catch(e){$('coachout').innerHTML='';toast(e.message,true)}
}
function copyText(){navigator.clipboard.writeText($('dtext').value).then(()=>toast('Copied'))}
async function mark(status){if(!current)return;
  try{await api('/api/draft/'+current+'/mark',{status});toast('Marked '+status);openDraft(current)}
  catch(e){toast(e.message,true)}}
async function dryRun(){if(!current)return;
  try{await saveText();const r=await api('/api/draft/'+current+'/publish',{dry_run:true});
    $('coachout').innerHTML='<h2 style="margin-top:18px">API payload (not posted)</h2><pre style="white-space:pre-wrap;color:var(--dim)">'+esc(JSON.stringify(r.body,null,2))+'</pre>'}
  catch(e){toast(e.message,true)}}
async function publishNow(){
  if(!current)return;
  if(!confirm('Publish this to LinkedIn now? It goes out under your name.'))return;
  const b=event.target;b.disabled=true;b.innerHTML='<span class="spin"></span>Publishing';
  try{await saveText();const r=await api('/api/draft/'+current+'/publish',{});
    toast('Published: '+(r.url||r.id));openDraft(current)}
  catch(e){toast(e.message,true)}
  finally{b.disabled=false;b.textContent='Publish'}
}
boot();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "lk"

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"https://{host}")

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", "inline")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _err(self, message: str, code: int = 400) -> None:
        self._json({"error": message}, code)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, *_args):
        pass

    # ── GET ──────────────────────────────────────────────────────────────

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
                return
            if path == "/api/state":
                self._json(
                    {
                        "name": publish.load_auth().get("name", ""),
                        "model": config.MODEL,
                        "examples": len(voice.examples(limit=10_000)),
                        "connected": bool(publish.load_auth().get("access_token")),
                    }
                )
                return
            if path == "/api/queue":
                self._json(
                    {
                        "pending": queue_mod.listing("pending-approval"),
                        "approved": queue_mod.listing("pending"),
                        "cap": publish.daily_reply_cap(),
                        "used_today": publish.daily_reply_count(),
                        "quiet": publish.in_quiet_hours(),
                    }
                )
                return
            if path == "/api/drafts":
                self._json(
                    [
                        {k: r.get(k) for k in ("id", "kind", "title", "status", "chars")}
                        for r in store.all_drafts()
                    ]
                )
                return
            if path.startswith("/api/draft/"):
                rest = path[len("/api/draft/") :].strip("/")
                parts = rest.split("/")
                if len(parts) == 2 and parts[1] == "image":
                    rec = store.find(parts[0])
                    img = rec.get("image") or {}
                    src = Path(img.get("path", ""))
                    if not src.is_file():
                        self._err("no image attached", 404)
                        return
                    ctype = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
                    self._send(200, src.read_bytes(), ctype)
                    return
                if len(parts) != 1:
                    self._err("not found", 404)
                    return
                rec = store.find(parts[0])
                findings = [{"level": lvl, "message": msg} for lvl, msg in safety.audit(rec)]
                self._json({"record": rec, "findings": findings})
                return
            self._err("not found", 404)
        except KeyError as exc:
            self._err(str(exc), 404)
        except Exception as exc:  # noqa: BLE001
            self._err(str(exc), 500)

    # ── POST ─────────────────────────────────────────────────────────────

    def do_POST(self):  # noqa: N802
        if not self._origin_ok():
            self._err("bad origin", 403)
            return
        path = urlparse(self.path).path
        data = self._body()
        try:
            if path == "/api/generate":
                self._generate(data)
                return
            if path == "/api/queue/approve":
                item = queue_mod.approve(str(data.get("id", "")))
                if not item:
                    self._err("No such pending item", 404)
                    return
                self._json({"ok": True, "item": item})
                return
            if path == "/api/queue/reject":
                ok = queue_mod.reject(str(data.get("id", "")))
                if not ok:
                    self._err("No such pending item", 404)
                    return
                self._json({"ok": True})
                return
            if path == "/api/inbox/check":
                summary = watch_mod.check_once(
                    post_urn=str(data.get("post", "")),
                    draft=True,
                )
                self._json(summary)
                return
            if path == "/api/reply":
                self._draft_reply(data)
                return
            if path.startswith("/api/draft/"):
                parts = path[len("/api/draft/") :].split("/")
                draft_id = parts[0]
                action = parts[1] if len(parts) > 1 else ""
                if action == "text":
                    rec = store.update_text(draft_id, data.get("text", ""))
                    self._json({"ok": True, "chars": rec["chars"]})
                    return
                if action == "mark":
                    status = data.get("status", "posted")
                    if status not in ("draft", "posted", "rejected"):
                        self._err("status must be draft, posted or rejected")
                        return
                    rec = store.set_status(draft_id, status)
                    self._json({"ok": True, "status": rec["status"]})
                    return
                if action == "image":
                    self._attach_image(draft_id, data)
                    return
                if action == "image-alt":
                    rec = store.find(draft_id)
                    img = rec.get("image") or {}
                    if not img.get("path"):
                        self._err("No image attached")
                        return
                    store.set_image(draft_id, img["path"], str(data.get("alt", ""))[:300])
                    self._json({"ok": True})
                    return
                if action == "image-remove":
                    rec = store.find(draft_id)
                    img = rec.get("image") or {}
                    store.clear_image(draft_id)
                    src = Path(img.get("path", ""))
                    uploads = (config.DATA / "uploads").resolve()
                    try:
                        if src.is_file() and uploads in src.resolve().parents:
                            src.unlink()
                    except OSError:
                        pass
                    self._json({"ok": True})
                    return
                if action == "humanize":
                    from . import humanize as hz

                    rec = store.find(draft_id)
                    cleaned, changes = hz.humanize(rec.get("text", ""))
                    if changes:
                        store.update_text(rec["id"], cleaned)
                    self._json(
                        {
                            "ok": True,
                            "changes": changes,
                            "hype": hz.hype_words(cleaned),
                            "openers": hz.repeated_openers(cleaned),
                        }
                    )
                    return
                if action == "coach":
                    from . import coach as coach_mod

                    rec = store.find(draft_id)
                    self._json(coach_mod.analyze(rec["text"]))
                    return
                if action == "publish":
                    self._publish(draft_id, bool(data.get("dry_run")))
                    return
            self._err("not found", 404)
        except KeyError as exc:
            self._err(str(exc), 404)
        except publish.APIError as exc:
            self._err(str(exc), 400)
        except Exception as exc:  # noqa: BLE001
            self._err(str(exc), 500)

    def _generate(self, data: dict) -> None:
        kind = data.get("kind", "post")
        if kind == "cert":
            post = posts.certificate(
                title=data.get("title", ""),
                issuer=data.get("issuer", ""),
                skills=data.get("skills", ""),
                story=data.get("story", ""),
                tone=data.get("tone", ""),
            )
            text = posts.render(post)
            rec = store.save("cert", data.get("title", ""), text, post)
        else:
            post = posts.topic(data.get("topic", ""), angle=data.get("angle", ""))
            text = posts.render(post)
            rec = store.save("post", data.get("topic", ""), text, post)
        self._json({"id": rec["id"]})

    def _attach_image(self, draft_id: str, data: dict) -> None:
        raw64 = data.get("data", "")
        if not isinstance(raw64, str) or not raw64:
            self._err("No image data")
            return
        if len(raw64) > 14 * 1024 * 1024:
            self._err("Image must be under 10 MB")
            return
        try:
            raw = base64.b64decode(raw64, validate=True)
        except Exception:  # noqa: BLE001
            self._err("That file is not valid image data")
            return
        if len(raw) > 10 * 1024 * 1024:
            self._err("Image must be under 10 MB")
            return
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = "png"
        elif raw.startswith(b"\xff\xd8\xff"):
            ext = "jpg"
        elif raw[:6] in (b"GIF87a", b"GIF89a"):
            ext = "gif"
        else:
            self._err("Only JPG, PNG or GIF images are supported")
            return

        uploads = config.DATA / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        rec = store.find(draft_id)
        target = uploads / f"{rec['id']}.{ext}"
        target.write_bytes(raw)
        store.set_image(rec["id"], str(target), str(data.get("alt", ""))[:300])
        self._json({"ok": True, "file": target.name})

    def _draft_reply(self, data: dict) -> None:
        comment = str(data.get("comment", "")).strip()
        author = str(data.get("author", "")).strip()
        url = str(data.get("url", "")).strip()
        post_text = str(data.get("post", "")).strip()

        if not comment:
            self._err("Paste the comment first")
            return
        if not url:
            self._err("Post URL is required")
            return

        from . import replied

        if author and replied.has_replied(url, author):
            self._err(f"{author} already got a reply on this post — skipping")
            return

        try:
            result = comments.reply_to_comment(post_text, comment, author)
            item = queue_mod.add(
                "comment",
                url,
                result["reply"],
                label=f"reply to {author or 'comment'}",
                post_urn=url,
                author=author,
            )
        except ValueError as exc:
            self._err(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._err(f"Drafting failed: {exc}")
            return

        self._json({"ok": True, "item": item, "reply": result["reply"], "warnings": comments.warnings(result)})

    def _publish(self, draft_id: str, dry_run: bool) -> None:
        rec = store.find(draft_id)
        blockers = [msg for lvl, msg in safety.audit(rec) if lvl == safety.HIGH]
        if blockers and not dry_run:
            self._err("Blocked by safety check: " + blockers[0], 400)
            return
        img = rec.get("image") or {}
        result = publish.publish_post(
            rec["text"],
            dry_run=dry_run,
            image_path=img.get("path", ""),
            alt_text=img.get("alt", ""),
        )
        if dry_run:
            self._json({"body": result["body"]})
            return
        store.set_status(rec["id"], "posted")
        self._json({"url": result.get("url", ""), "id": result.get("id", "")})


def _lan_ip() -> str:
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return ""


def _self_test(port: int) -> None:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=8) as resp:
            resp.read(200)
            code = resp.status
        print(f"self-check  OK    server answered HTTP {code}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"self-check  FAIL  {exc}", flush=True)


def serve(port: int = 8080, open_browser: bool = True, host: str = "127.0.0.1") -> None:
    server = None
    last_error = None
    for candidate in [port] + [p for p in range(port + 1, port + 11) if p != port]:
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            break
        except OSError as exc:
            last_error = exc
            continue
    if server is None:
        raise SystemExit(f"Could not bind a port near {port}: {last_error}")

    actual = server.server_address[1]
    url = f"http://127.0.0.1:{actual}/"
    print(f"lk web running at {url}", flush=True)
    if actual != port:
        print(f"(port {port} was busy, using {actual} — open the URL above, not {port})", flush=True)
    if host == "0.0.0.0":
        ip = _lan_ip()
        if ip:
            print(f"From Windows:   http://{ip}:{actual}/", flush=True)
        print("Reachable from your network on this port — stop it when you're done.", flush=True)
    else:
        print("Windows browser can't reach it? Restart with: lk web --host 0.0.0.0", flush=True)
    print("If the browser downloads a file instead of showing a page, you opened", flush=True)
    print("a file path or the wrong port. Copy the exact URL above into the", flush=True)
    print("address bar and press Enter.", flush=True)
    print("Ctrl+C to stop.", flush=True)
    threading.Timer(0.8, _self_test, args=(actual,)).start()
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.", flush=True)
    finally:
        server.server_close()
