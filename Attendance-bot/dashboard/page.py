"""Dashboard single-page UI (plain HTML/JS, talks to the JSON API in server.py)."""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Attendance Bot</title>
<style>
  :root { --bg:#0a0a0f; --surface:#12121a; --surface2:#181824; --border:#252538; --accent:#7c3aed;
          --accent2:#06d6a0; --warn:#f59e0b; --danger:#ef4444; --text:#e2e8f0; --muted:#7c8aa0; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,Arial,sans-serif; min-height:100vh; padding:1.5rem 2rem 4rem; }
  .mono { font-family:'JetBrains Mono',Consolas,monospace; }
  header { display:flex; align-items:center; gap:1rem; margin-bottom:1.2rem; padding-bottom:1rem; border-bottom:1px solid var(--border); }
  .dot { width:10px; height:10px; border-radius:50%; background:var(--accent2); box-shadow:0 0 10px var(--accent2); animation:pulse 1.5s infinite; }
  .dot.off { background:var(--danger); box-shadow:0 0 10px var(--danger); animation:none; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  h1 { font-size:1.4rem; font-weight:800; letter-spacing:-.02em; }
  .sub { color:var(--muted); font-size:.8rem; }
  .spacer { flex:1; }
  .pill { padding:.25rem .8rem; border-radius:999px; font-size:.75rem; font-weight:700; background:#1a2a3a; color:#7dd3fc; }
  .pill.in_class { background:#14302a; color:var(--accent2); }
  nav { display:flex; gap:.4rem; margin-bottom:1.2rem; }
  nav button { background:transparent; border:1px solid var(--border); color:var(--muted); padding:.5rem 1.1rem; border-radius:8px; cursor:pointer; font-size:.9rem; }
  nav button.active { background:var(--accent); border-color:var(--accent); color:#fff; }
  .tab { display:none; } .tab.active { display:block; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1rem; margin-bottom:1.2rem; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:1.1rem 1.3rem; margin-bottom:1rem; }
  .grid .card { margin-bottom:0; }
  .label { font-size:.68rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; margin-bottom:.4rem; }
  .value { font-size:1.25rem; font-weight:700; }
  h2 { font-size:1rem; margin-bottom:.8rem; }
  .hint { color:var(--muted); font-size:.8rem; margin-top:.3rem; }
  table { width:100%; border-collapse:collapse; font-size:.85rem; }
  th { text-align:left; color:var(--muted); font-weight:500; font-size:.7rem; text-transform:uppercase; padding:.4rem .4rem; border-bottom:1px solid var(--border); }
  td { padding:.45rem .4rem; border-bottom:1px solid var(--border); vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  .empty { color:var(--muted); font-style:italic; padding:1rem 0; text-align:center; }
  input, select, textarea { background:var(--surface2); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:.5rem .65rem; font:inherit; font-size:.88rem; width:100%; }
  input:focus, select:focus, textarea:focus { outline:none; border-color:var(--accent); }
  input[type=checkbox] { width:auto; }
  textarea { min-height:110px; resize:vertical; }
  .linkin { min-width:260px; font-family:Consolas,monospace; font-size:.8rem; }
  .linkin.missing { border-color:var(--warn); }
  .row { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.7rem; margin-bottom:.7rem; }
  .row.wide { grid-template-columns:1fr; }
  label.f { display:block; font-size:.72rem; color:var(--muted); margin-bottom:.25rem; }
  .btn { background:var(--accent); color:#fff; border:none; border-radius:8px; padding:.5rem 1.1rem; cursor:pointer; font-size:.88rem; font-weight:600; }
  .btn:hover { filter:brightness(1.15); }
  .btn.ghost { background:transparent; border:1px solid var(--border); color:var(--text); }
  .btn.danger { background:transparent; border:1px solid #5a2323; color:var(--danger); }
  .btn.sm { padding:.25rem .65rem; font-size:.78rem; }
  .btn.green { background:#0e8f6b; }
  .badge { display:inline-block; padding:.12rem .6rem; border-radius:999px; font-size:.72rem; font-weight:700; background:#1a3a4a; color:#38bdf8; }
  .badge.zoom { background:#1a2a4a; color:#818cf8; } .badge.ok { background:#14302a; color:var(--accent2); }
  .badge.warn { background:#3a2e12; color:var(--warn); } .badge.bad { background:#2a1a1a; color:var(--danger); }
  .alert { border-left:3px solid var(--warn); background:#241e10; padding:.5rem .8rem; border-radius:6px; margin-bottom:.4rem; font-size:.85rem; }
  .alert.failure { border-color:var(--danger); background:#2a1515; }
  .cap { background:var(--surface2); border-radius:8px; padding:.7rem; font-size:.9rem; min-height:2.5rem; white-space:pre-wrap; }
  .actions { display:flex; gap:.4rem; justify-content:flex-end; }
  .check { display:flex; align-items:center; gap:.5rem; margin:.35rem 0; font-size:.9rem; }
  .notes-item { display:flex; align-items:center; gap:.6rem; padding:.6rem 0; border-bottom:1px solid var(--border); flex-wrap:wrap; }
  .notes-item:last-child { border-bottom:none; }
  .notes-item a { color:#7dd3fc; text-decoration:none; font-size:.85rem; } .notes-item a:hover { text-decoration:underline; }
  #toast { position:fixed; bottom:1.2rem; right:1.2rem; background:#1d2a27; border:1px solid var(--accent2); color:var(--text); padding:.7rem 1.1rem; border-radius:10px; display:none; max-width:420px; z-index:9; }
  #toast.err { background:#2a1717; border-color:var(--danger); }
  .tbl-wrap { overflow-x:auto; }
</style>
</head>
<body>
<header>
  <div class="dot" id="dot"></div>
  <div><h1>Attendance Bot</h1><div class="sub mono" id="who">…</div></div>
  <div class="spacer"></div>
  <span class="pill" id="statusPill">IDLE</span>
</header>

<nav>
  <button data-tab="overview" class="active">Overview</button>
  <button data-tab="schedule">Schedule</button>
  <button data-tab="notes">Notes</button>
  <button data-tab="settings">Settings</button>
</nav>

<!-- ───────── OVERVIEW ───────── -->
<section class="tab active" id="tab-overview">
  <div class="grid">
    <div class="card"><div class="label">Current class</div><div class="value" id="curClass">—</div></div>
    <div class="card"><div class="label">Attendance</div><div class="value" id="curAtt">—</div></div>
    <div class="card"><div class="label">Slides captured</div><div class="value" id="curSlides">0</div></div>
    <div class="card"><div class="label">Last notes saved</div><div class="value" style="font-size:.85rem" id="lastNotes">—</div></div>
  </div>
  <div class="card"><h2>Alerts</h2><div id="alerts"><div class="empty">Nothing yet.</div></div></div>
  <div class="card"><h2>Live caption</h2><div class="cap" id="lastCap" dir="auto">—</div></div>
  <div class="card"><h2>Attendance history</h2><div id="history"></div></div>
</section>

<!-- ───────── SCHEDULE ───────── -->
<section class="tab" id="tab-schedule">
  <div class="card">
    <h2>Quick join (join a meeting right now)</h2>
    <div class="row">
      <div style="grid-column:span 2"><label class="f">Meeting link</label><input id="qjLink" placeholder="https://meet.google.com/abc-defg-hij"></div>
      <div><label class="f">Subject</label><input id="qjSubject" placeholder="Quick join"></div>
      <div><label class="f">Stay for (minutes)</label><input id="qjDur" type="number" value="60" min="1"></div>
    </div>
    <button class="btn green" onclick="quickJoin()">Join now</button>
    <div class="hint">The bot picks it up within ~10 seconds, joins, and the entry removes itself afterwards.</div>
  </div>

  <div class="card">
    <h2>Weekly timetable</h2>
    <div class="hint" style="margin:-.4rem 0 .8rem">Paste a link into the box on any row and press Enter (or click away) — it saves instantly and the bot reloads the schedule by itself.</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Day</th><th>Time</th><th>Min</th><th>Subject</th><th>Platform</th><th>Meeting link</th><th></th></tr></thead>
      <tbody id="classRows"></tbody>
    </table></div>
  </div>

  <div class="card">
    <h2 id="formTitle">Add a class</h2>
    <input type="hidden" id="fId">
    <div class="row">
      <div><label class="f">Day</label><select id="fDay"></select></div>
      <div><label class="f">Start time</label><input id="fTime" type="time"></div>
      <div><label class="f">Duration (min)</label><input id="fDur" type="number" value="50" min="1"></div>
      <div><label class="f">Subject</label><input id="fSubject"></div>
      <div><label class="f">Platform</label><select id="fPlat"><option value="meet">Google Meet</option><option value="zoom">Zoom</option></select></div>
      <div><label class="f">Captions language</label><select id="fCap"><option value="">Default (Settings)</option><option value="urdu">Urdu</option><option value="english">English</option><option value="keep">Keep Meet's own</option></select></div>
    </div>
    <div class="row wide"><div><label class="f">Meeting link</label><input id="fLink" placeholder="https://…"></div></div>
    <button class="btn" onclick="saveClass()">Save class</button>
    <button class="btn ghost" onclick="resetForm()">Clear</button>
  </div>
</section>

<!-- ───────── NOTES ───────── -->
<section class="tab" id="tab-notes">
  <div class="card"><h2>Class notes</h2><div class="hint" style="margin:-.4rem 0 .6rem">Saved after every Meet class: organized AI study notes, when available, plus the original transcript. Open a class to view its PDF beside a lecture-grounded study chat.</div><div id="notesList"></div></div>
</section>

<!-- ───────── SETTINGS ───────── -->
<section class="tab" id="tab-settings">
  <div class="card">
    <h2>You</h2>
    <div class="row">
      <div><label class="f">Name</label><input id="sName"></div>
      <div><label class="f">Roll number</label><input id="sRoll"></div>
      <div><label class="f">Leave if fewer people than</label><input id="sMinP" type="number" min="0"></div>
    </div>
    <div class="row wide"><div>
      <label class="f">Name spellings the captions might produce (one per line)</label>
      <textarea id="sNames" dir="auto"></textarea>
      <div class="hint">Add Urdu + English variants. Check the live caption on the Overview tab during a test to see how your name actually appears.
      "Leave if fewer than N" — the bot leaves a meeting when fewer than N people stay for 2 minutes (use 2 for testing, 6+ to auto-leave when a class empties).</div>
    </div></div>
  </div>

  <div class="card">
    <h2>Features</h2>
    <label class="check"><input type="checkbox" id="fNotes"> Save lecture transcript to notes/</label>
    <label class="check"><input type="checkbox" id="fAI"> Generate organized AI study notes at class end (needs API key below)</label>
    <label class="check"><input type="checkbox" id="fCalled"> Sound + popup when my name / roll number is called</label>
    <label class="check"><input type="checkbox" id="fSlides"> Capture slides and build a PDF with notes</label>
    <label class="check"><input type="checkbox" id="fWhisper"> Locally transcribe meeting playback with Whisper (no API key)</label>
    <div class="hint">Captures all audio from the default Windows speaker output using WASAPI loopback; Meet captions still drive attendance detection. The free Whisper base model downloads on first use and runs locally on CPU. Keep meeting audio unmuted.</div>
    <div class="row" style="margin-top:.6rem">
      <div><label class="f">Captions language (what the teacher speaks)</label>
        <select id="fCapLang"><option value="urdu">Urdu (understands English words too)</option><option value="english">English</option><option value="keep">Keep Meet's own setting</option></select></div>
      <div><label class="f">Write my AI notes in</label>
        <select id="fNotesLang"><option>English</option><option>Urdu</option><option>Roman Urdu</option></select></div>
      <div><label class="f">AI notes detail</label>
        <select id="fPdfDetail"><option value="concise">Concise</option><option value="detailed">Detailed (recommended)</option></select></div>
      <div><label class="f">PDF paper size</label>
        <select id="fPdfPaper"><option value="A4">A4</option><option value="Letter">US Letter</option></select></div>
      <div><label class="f">Snapshot every (sec) when the screen is a video / whiteboard (0 = off)</label><input id="fKey" type="number" min="0" max="300"></div>
    </div>
    <div class="hint">The PDF leads with structured notes (concept headings, explanations, formulas, and examples). The complete transcript is always kept separately; optionally append it to the PDF below.</div>
    <label class="check"><input type="checkbox" id="fPdfTranscript"> Append the full transcript to the PDF (also saved separately)</label>
    <div class="hint">Meet can caption only one language at a time. Mixed Urdu + English lectures work in either mode; override the language for a single class in Schedule → Edit.</div>
    <div class="row" style="margin-top:.6rem">
      <div><label class="f">Slide capture mode</label>
        <select id="fMode"><option value="auto">auto (only when someone presents)</option><option value="always">always (largest video)</option><option value="off">off</option></select></div>
      <div><label class="f">Check for new slide every (sec)</label><input id="fInt" type="number" min="2" max="60"></div>
    </div>
  </div>

  <div class="card">
    <h2>AI notes provider</h2>
    <div class="row">
      <div><label class="f">Provider</label>
        <select id="aProv" onchange="showProv()"><option value="anthropic">Anthropic (Claude)</option><option value="deepseek">DeepSeek</option><option value="gemini">Google Gemini</option></select></div>
      <div><label class="f">API key (for the provider selected)</label><input id="aKey" type="password" autocomplete="off" placeholder="paste key…"></div>
      <div><label class="f">Model (blank = default)</label><input id="aModel"></div>
    </div>
    <label class="check"><input type="checkbox" id="aClear"> Remove the saved key</label>
    <div class="hint" id="aHint"></div>
  </div>

  <button class="btn" onclick="saveSettings()">Save settings</button>
</section>

<div id="toast"></div>

<script>
const DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
let CFG = null;

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function toast(msg, err) {
  const t = $("toast"); t.textContent = msg; t.className = err ? "err" : "";
  t.style.display = "block"; clearTimeout(toast._t);
  toast._t = setTimeout(() => t.style.display = "none", err ? 6000 : 2500);
}

async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(url, opt); } catch (e) { toast("Bot not reachable", true); throw e; }
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) { toast(data.error || ("Error " + r.status), true); throw new Error(data.error || r.status); }
  return data;
}

/* ───── tabs ───── */
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "notes") loadNotes();
});

/* ───── config / schedule ───── */
async function loadConfig() {
  CFG = await api("GET", "/api/config");
  $("who").textContent = (CFG.student.name || "—") + " · " + (CFG.student.roll_no || "—");
  renderClasses(); fillSettings();
}

function renderClasses() {
  const rows = CFG.classes.map(c => `
    <tr>
      <td>${esc(c.day)}</td><td class="mono">${esc(c.time)}</td><td>${esc(c.duration)}</td>
      <td>${esc(c.subject)} ${c.captions ? '<span class="badge">' + esc(c.captions) + ' captions</span>' : ''} ${c._test ? '<span class="badge warn">TEST</span>' : ''}${c.once ? ' <span class="badge warn">ONE-OFF</span>' : ''}</td>
      <td><span class="badge ${c.platform === "zoom" ? "zoom" : ""}">${esc(c.platform)}</span></td>
      <td><input class="linkin ${c.link ? "" : "missing"}" value="${esc(c.link)}" placeholder="paste link here…"
                 onchange="setLink('${esc(c.id)}', this)"></td>
      <td><div class="actions">
        <button class="btn ghost sm" onclick="editClass('${esc(c.id)}')">Edit</button>
        <button class="btn danger sm" onclick="deleteClass('${esc(c.id)}')">Delete</button></div></td>
    </tr>`).join("");
  $("classRows").innerHTML = rows || '<tr><td colspan="7" class="empty">No classes yet — add one below.</td></tr>';
}

async function setLink(id, input) {
  const c = CFG.classes.find(x => x.id === id); if (!c) return;
  const body = { day: c.day, time: c.time, duration: c.duration, subject: c.subject, platform: c.platform, link: input.value.trim(), captions: c.captions || "" };
  if (/zoom\.us/.test(body.link)) body.platform = "zoom";
  else if (/meet\.google\.com/.test(body.link)) body.platform = "meet";
  try { await api("PUT", "/api/classes/" + id, body); toast("Link saved for " + c.subject); await loadConfig(); }
  catch (e) { input.focus(); }
}

function editClass(id) {
  const c = CFG.classes.find(x => x.id === id); if (!c) return;
  $("fId").value = id; $("fDay").value = c.day; $("fTime").value = c.time; $("fDur").value = c.duration;
  $("fSubject").value = c.subject; $("fPlat").value = c.platform; $("fLink").value = c.link || ""; $("fCap").value = c.captions || "";
  $("formTitle").textContent = "Edit class — " + c.subject;
  $("fSubject").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetForm() {
  $("fId").value = ""; $("fSubject").value = ""; $("fLink").value = ""; $("fTime").value = "";
  $("fDur").value = 50; $("fPlat").value = "meet"; $("fCap").value = ""; $("formTitle").textContent = "Add a class";
}

async function saveClass() {
  const body = { day: $("fDay").value, time: $("fTime").value, duration: $("fDur").value,
                 subject: $("fSubject").value, platform: $("fPlat").value, link: $("fLink").value, captions: $("fCap").value };
  const id = $("fId").value;
  try {
    if (id) await api("PUT", "/api/classes/" + id, body); else await api("POST", "/api/classes", body);
    toast("Saved"); resetForm(); await loadConfig();
  } catch (e) {}
}

async function deleteClass(id) {
  const c = CFG.classes.find(x => x.id === id);
  if (!confirm("Delete " + (c ? c.subject + " (" + c.day + " " + c.time + ")" : "this class") + "?")) return;
  try { await api("DELETE", "/api/classes/" + id); toast("Deleted"); await loadConfig(); } catch (e) {}
}

async function quickJoin() {
  try {
    await api("POST", "/api/quickjoin", { link: $("qjLink").value, subject: $("qjSubject").value, duration: $("qjDur").value });
    toast("Queued — the bot will join within ~10 seconds"); $("qjLink").value = ""; await loadConfig();
  } catch (e) {}
}

/* ───── settings ───── */
function fillSettings() {
  const s = CFG.student, f = CFG.features;
  $("sName").value = s.name || ""; $("sRoll").value = s.roll_no || "";
  $("sNames").value = (s.urdu_names || []).join("\n");
  $("sMinP").value = CFG.settings.min_participants;
  $("fNotes").checked = f.notes; $("fAI").checked = f.ai_summary; $("fCalled").checked = f.called_alert; $("fSlides").checked = f.slides; $("fWhisper").checked = f.whisper_transcription;
  $("fMode").value = f.slide_mode; $("fInt").value = f.slide_interval;
  $("fCapLang").value = f.caption_language; $("fNotesLang").value = f.notes_language; $("fKey").value = f.keyframe_interval;
  $("fPdfDetail").value = f.pdf_detail; $("fPdfPaper").value = f.pdf_paper_size;
  $("fPdfTranscript").checked = f.pdf_include_transcript;
  $("aProv").value = CFG.ai.provider; showProv();
}

function showProv() {
  const p = CFG.ai.providers[$("aProv").value];
  $("aModel").value = p.model || ""; $("aModel").placeholder = p.default_model;
  $("aKey").value = ""; $("aClear").checked = false;
  $("aHint").textContent = p.has_key
    ? ("A " + p.label + " key is saved (" + p.key_hint + "). Leave the box empty to keep it.")
    : ("No " + p.label + " key saved — AI summaries are skipped for this provider (the PDF and transcript are still built).");
}

async function saveSettings() {
  const body = {
    student: { name: $("sName").value, roll_no: $("sRoll").value, urdu_names: $("sNames").value },
    settings: { min_participants: $("sMinP").value },
    features: { notes: $("fNotes").checked, ai_summary: $("fAI").checked, called_alert: $("fCalled").checked,
                whisper_transcription: $("fWhisper").checked,
                slides: $("fSlides").checked, slide_mode: $("fMode").value, slide_interval: $("fInt").value,
                caption_language: $("fCapLang").value, notes_language: $("fNotesLang").value, keyframe_interval: $("fKey").value,
                pdf_detail: $("fPdfDetail").value, pdf_paper_size: $("fPdfPaper").value,
                pdf_include_transcript: $("fPdfTranscript").checked },
    ai: { provider: $("aProv").value, model: $("aModel").value, api_key: $("aKey").value, clear_key: $("aClear").checked },
  };
  try { await api("POST", "/api/settings", body); toast("Settings saved — applies from the next class"); await loadConfig(); } catch (e) {}
}

/* ───── notes ───── */
async function loadNotes() {
  const list = await api("GET", "/api/notes");
  $("notesList").innerHTML = list.length ? list.map(n => `
    <div class="notes-item">
      <b>${esc(n.lecture_title || n.subject)}</b> <span class="sub mono">${esc(n.date)} ${esc(n.time)}</span>
      ${n.slides ? `<span class="badge">${n.slides} slides</span>` : ""}
      ${n.summary ? '<span class="badge ok">AI summary</span>' : ""}
      ${n.done ? "" : '<span class="badge warn">in progress</span>'}
      <span class="spacer"></span>
      ${n.pdf ? `<a href="/notes/${encodeURI(n.folder)}/notes.pdf" target="_blank"><b>Lecture notes PDF</b></a>` : ""}
      ${(!n.pdf && n.html) ? `<a href="/notes/${encodeURI(n.folder)}/notes.html" target="_blank"><b>Lecture notes</b> (open &amp; Print → PDF)</a>` : ""}
      ${(n.pdf || n.html) && n.done ? `<a href="/notes/${encodeURI(n.folder)}/study" target="_blank"><b>Open notes + study chat</b></a>` : ""}
      <a href="/notes/${encodeURI(n.folder)}/transcript.md" target="_blank">Transcript</a>
      ${n.corrected_transcript ? `<a href="/notes/${encodeURI(n.folder)}/transcript_corrected.md" target="_blank">AI-corrected transcript</a>` : ""}
    </div>`).join("") : '<div class="empty">No notes yet — they appear after your first Meet class.</div>';
}

/* ───── live state ───── */
async function pollState() {
  try {
    const s = await api("GET", "/api/state");
    const st = (s.status || "idle");
    $("statusPill").textContent = st.toUpperCase().replace("_", " "); $("statusPill").className = "pill " + st;
    $("dot").classList.remove("off");
    const c = s.current_class;
    $("curClass").textContent = c ? c.subject : "—";
    $("curAtt").textContent = c ? (s.attendance_marked ? "✅ Marked" : "⏳ Waiting") : "—";
    $("curSlides").textContent = s.slide_count || 0;
    $("lastNotes").textContent = s.last_notes || "—";
    $("lastCap").textContent = s.last_caption || "—";
    const al = (s.alerts || []).slice().reverse();
    $("alerts").innerHTML = al.length ? al.map(a => `<div class="alert ${esc(a.kind)}"><b>${esc(a.time)}</b> · ${esc(a.subject)} — ${esc(a.text)}</div>`).join("")
                                      : '<div class="empty">Nothing yet.</div>';
  } catch (e) { $("dot").classList.add("off"); }
}

async function loadHistory() {
  const h = await api("GET", "/api/history");
  $("history").innerHTML = h.length ? `<table><thead><tr><th>Date</th><th>Time</th><th>Subject</th><th>Platform</th><th>Status</th></tr></thead><tbody>` +
    h.map(e => `<tr><td>${esc((e.timestamp||"").slice(0,10))}</td><td>${esc((e.timestamp||"").slice(11,16))}</td><td>${esc(e.subject)}</td>
      <td><span class="badge ${e.platform === "zoom" ? "zoom" : ""}">${esc(e.platform)}</span></td>
      <td><span class="badge ${e.status === "present" ? "ok" : (e.status === "failed" ? "bad" : "warn")}">${esc(e.status)}</span></td></tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No sessions logged yet.</div>';
}

DAYS.forEach(d => { const o = document.createElement("option"); o.value = o.textContent = d; $("fDay").appendChild(o); });
loadConfig(); pollState(); loadHistory();
setInterval(pollState, 3000); setInterval(loadHistory, 30000);
</script>
</body>
</html>
"""
