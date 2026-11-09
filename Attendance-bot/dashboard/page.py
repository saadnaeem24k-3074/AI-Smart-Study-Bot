"""Dashboard single-page UI (plain HTML/JS, talks to the JSON API in server.py)."""

PAGE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Attendance Bot</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#f3f4f6;--panel:#fff;--sunk:#eceef2;--line:#dde1e8;--ink:#14181f;--mute:#586170;--acc:#2447d6;--mark:#ffe14d;
--ok:#12805c;--warn:#9a5b00;--bad:#c0392b;--e:cubic-bezier(.2,.7,.2,1);color-scheme:light}
[data-theme=dark]{--bg:#0e1116;--panel:#161a21;--sunk:#1d222b;--line:#272d38;--ink:#e9ecf2;--mute:#9aa3b2;--acc:#8ba6ff;--mark:#6b5a0f;
--ok:#4cd2a0;--warn:#f0b955;--bad:#ff8a7a;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Hanken Grotesk","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.mono{font-family:"IBM Plex Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.mut{color:var(--mute);font-size:13px}
.ic{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
.shell{display:grid;grid-template-columns:224px minmax(0,1fr);min-height:100vh}
.rail{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:28px;padding:24px 16px;background:var(--panel);border-right:1px solid var(--line)}
.brand{display:flex;gap:10px;align-items:center;padding:0 8px;font-weight:800;font-size:16px;letter-spacing:-.01em}
.logo{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--ink);color:var(--bg)}
nav{position:relative;display:flex;flex-direction:column;gap:2px}
.nb{position:relative;z-index:1;display:flex;align-items:center;gap:12px;padding:10px 12px;border:0;border-radius:9px;background:none;color:var(--mute);font-weight:600;text-align:left;cursor:pointer;transition:color .2s}
.nb:hover,.nb.on{color:var(--ink)}.nb.on .ic{color:var(--acc)}
.pill{position:absolute;z-index:0;left:0;top:0;border-radius:9px;background:var(--sunk)}
.pill.ready{transition:transform .34s var(--e),width .34s var(--e),height .34s var(--e)}
.who{margin-top:auto;padding:0 8px}.who b{display:block}
.main{width:100%;max-width:1160px;padding:28px clamp(16px,4vw,48px) 64px}
.top{display:flex;align-items:center;gap:12px;margin-bottom:24px}
.top h1{margin:0;font-size:26px;font-weight:700;letter-spacing:-.02em}.sp{flex:1}
.chip{display:inline-flex;align-items:center;gap:7px;padding:4px 11px;border-radius:99px;background:var(--sunk);color:var(--mute);font-size:13px;font-weight:600;white-space:nowrap}
.chip i{width:7px;height:7px;border-radius:50%;background:currentColor}
.chip.ok,.s-in_class{color:var(--ok);background:color-mix(in srgb,var(--ok) 13%,var(--panel))}
.chip.warn,.s-waiting,.s-joining,.s-generating_notes{color:var(--warn);background:color-mix(in srgb,var(--warn) 14%,var(--panel))}
.chip.bad,.s-offline{color:var(--bad);background:color-mix(in srgb,var(--bad) 12%,var(--panel))}
.chip.acc{color:var(--acc);background:color-mix(in srgb,var(--acc) 12%,var(--panel))}
.s-in_class i{animation:beat 1.6s infinite}.s-waiting i,.s-joining i,.s-generating_notes i{animation:blink 1.2s infinite}
@keyframes beat{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--ok) 45%,transparent)}70%,100%{box-shadow:0 0 0 7px transparent}}
@keyframes blink{50%{opacity:.3}}
.icb{display:inline-grid;place-items:center;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel);cursor:pointer;transition:background .2s,transform .12s}
.icb:hover{background:var(--sunk)}.icb:active{transform:scale(.92)}.icb.bad:hover{color:var(--bad)}
#themeBtn .ic{transition:transform .5s var(--e)}#themeBtn.spin .ic{transform:rotate(360deg)}
.tab{display:none}.tab.on{display:block;animation:fade .22s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}}
.intro .rv{animation:rise .6s var(--e) both;animation-delay:calc(var(--i,0)*90ms)}
@keyframes rise{from{opacity:0;transform:translateY(12px)}}
.now{display:grid;grid-template-columns:1fr auto;gap:8px 24px;align-items:end;margin-bottom:16px;padding:28px 28px 0;overflow:hidden;border:1px solid var(--line);border-radius:20px;background:var(--panel)}
.now h2{margin:4px 0 6px;font-size:clamp(30px,5vw,50px);font-weight:800;line-height:1.1;letter-spacing:-.03em}
.mark{position:relative;z-index:0;display:inline-block}
.mark::before{content:"";position:absolute;z-index:-1;left:-.12em;right:-.12em;bottom:.04em;height:.5em;background:var(--mark);transform:scaleX(0);transform-origin:left;transition:transform .8s var(--e)}
.mark.on::before{transform:scaleX(1)}
.wave{display:flex;align-items:flex-end;gap:4px;height:52px;padding-bottom:6px}
.wave i{width:5px;height:100%;border-radius:3px;background:var(--line);transform:scaleY(.18);transform-origin:bottom;transition:background .3s}
.wave.on i{background:var(--acc);animation:eq .9s ease-in-out infinite alternate}
.wave i:nth-child(2n){animation-duration:1.15s}.wave i:nth-child(3n){animation-duration:.7s}
.wave i:nth-child(2){animation-delay:-.2s}.wave i:nth-child(3){animation-delay:-.5s}.wave i:nth-child(4){animation-delay:-.1s}
.wave i:nth-child(5){animation-delay:-.6s}.wave i:nth-child(6){animation-delay:-.3s}.wave i:nth-child(7){animation-delay:-.45s}
@keyframes eq{from{transform:scaleY(.18)}to{transform:scaleY(1)}}
.facts{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);margin:18px -28px 0;border-top:1px solid var(--line)}
.fact{padding:16px 28px}.fact+.fact{border-left:1px solid var(--line)}
.fact b{display:block;font-size:22px;font-weight:700;letter-spacing:-.02em;overflow-wrap:anywhere}
.two{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:16px}
.card{margin-bottom:16px;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
.card h2,.acc-h{margin:0;font-size:17px;font-weight:700;letter-spacing:-.01em}
.head{display:flex;align-items:flex-start;gap:12px;margin-bottom:16px}.head>div:first-child{flex:1}
.cap{min-height:84px;padding:2px 0 2px 16px;border-left:3px solid var(--acc);font-size:18px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.cap.new{animation:capin .4s var(--e)}@keyframes capin{from{opacity:.2;transform:translateX(-6px)}}
.al{margin-bottom:8px;padding:10px 12px;border-left:3px solid var(--warn);border-radius:8px;background:var(--sunk);font-size:14px}.al.failure{border-color:var(--bad)}
.empty{padding:26px 12px;text-align:center;color:var(--mute);border:1px dashed var(--line);border-radius:12px}.empty b{display:block;color:var(--ink)}
.sk{height:48px;margin-bottom:8px;border-radius:10px;background:var(--sunk);animation:blink 1.2s infinite}
.bar{display:flex;gap:10px;margin-bottom:14px}.bar>*{max-width:260px}
input,select,textarea{width:100%;min-width:0;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--panel);transition:border-color .2s}
input:hover,select:hover{border-color:var(--mute)}input:focus,select:focus{border-color:var(--acc)}
.row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:14px}
label.f{display:block;margin-bottom:5px;color:var(--mute);font-size:13px;font-weight:600}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;padding:0 16px;border:1px solid var(--ink);border-radius:9px;background:var(--ink);color:var(--bg);font-weight:650;cursor:pointer;transition:transform .12s,opacity .2s,background .2s}
.btn:hover{opacity:.88}.btn:active{transform:scale(.97)}.btn:disabled{opacity:.55;cursor:wait}
.btn.ghost{border-color:var(--line);background:transparent;color:var(--ink)}.btn.ghost:hover{background:var(--sunk);opacity:1}
.btn.danger{border-color:var(--bad);background:var(--bad);color:#fff}
.btn.busy::before{content:"";width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:rot .7s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
.acc-h{display:flex;align-items:center;gap:12px;width:100%;padding:18px 22px;border:0;background:none;cursor:pointer;text-align:left}
.acc-h .chev{margin-left:auto;transition:transform .3s var(--e)}.acc.open>.acc-h .chev{transform:rotate(180deg)}
.acc-b{display:grid;grid-template-rows:0fr;transition:grid-template-rows .3s var(--e)}.acc.open>.acc-b{grid-template-rows:1fr}
.acc-i{min-height:0;overflow:hidden}.acc:not(.open)>.acc-b>.acc-i{visibility:hidden;transition:visibility 0s .3s}
.acc.card{padding:0}.pad{padding:0 22px 22px}
.day{margin-bottom:10px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.day .acc-h{padding:13px 16px;font-size:15px}.day.today{border-color:var(--ink)}
.day .pad{padding:0 16px 6px}
.cr{display:grid;grid-template-columns:64px minmax(150px,1fr) minmax(190px,1.2fr) auto;gap:14px;align-items:center;padding:12px 8px;border-top:1px solid var(--line);transition:background .2s}
.cr:hover{background:var(--sunk)}.cr.next{box-shadow:inset 3px 0 var(--mark);padding-left:14px}
.ct{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-weight:700}
.lnk input{padding:8px 10px;font-size:12px}.lnk input.miss{border-style:dashed;border-color:var(--warn)}
.acts{display:flex;gap:6px}
.nr{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;padding:15px 6px;border-top:1px solid var(--line);position:relative}
.nr:hover{background:var(--sunk)}.ni{flex:1;min-width:230px}.ni b{display:block;font-size:16px}
.nl{display:flex;flex-wrap:wrap;gap:4px}
.nl a{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;color:var(--acc);font-size:13px;font-weight:650;text-decoration:none;transition:background .2s}
.nl a:hover{background:color-mix(in srgb,var(--acc) 12%,var(--panel))}
.prog{position:absolute;left:6px;right:6px;bottom:6px;height:3px;overflow:hidden;border-radius:3px;background:var(--sunk)}
.prog::after{content:"";display:block;width:30%;height:100%;border-radius:3px;background:var(--warn);animation:slide 1.4s var(--e) infinite alternate}
@keyframes slide{to{transform:translateX(233%)}}
.gh{display:flex;align-items:center;gap:10px;margin:22px 0 4px;font-size:14px;font-weight:700}
.tg-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.tog{display:flex;align-items:center;gap:12px;padding:12px;border:1px solid var(--line);border-radius:11px;cursor:pointer;transition:border-color .2s}
.tog:hover{border-color:var(--mute)}.tog input{position:absolute;opacity:0;width:1px;height:1px}
.sw{position:relative;flex:none;width:40px;height:24px;border-radius:99px;background:var(--line);transition:background .25s}
.sw::after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0004;transition:transform .3s var(--e)}
.tog input:checked+.sw{background:var(--acc)}.tog input:checked+.sw::after{transform:translateX(16px)}
.tog input:focus-visible+.sw{outline:2px solid var(--acc);outline-offset:2px}
.tog b{display:block;font-size:14px}.tog small{display:block;color:var(--mute);font-size:12px;line-height:1.4}
.tags{display:flex;flex-wrap:wrap;gap:7px;margin:10px 0}
.tag{display:inline-flex;align-items:center;gap:6px;padding:4px 6px 4px 11px;border-radius:99px;background:var(--sunk);font-size:14px;animation:pop .25s var(--e)}
.tag button{display:grid;place-items:center;width:20px;height:20px;border:0;border-radius:50%;background:none;cursor:pointer}.tag button:hover{background:var(--line)}
.save{position:sticky;bottom:16px;z-index:5;display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:var(--panel);box-shadow:0 8px 28px rgba(10,12,16,.12)}
.tw{overflow:auto}table{width:100%;border-collapse:collapse}
th,td{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-size:13px;font-weight:600}tbody tr{transition:background .2s}tbody tr:hover{background:var(--sunk)}tr:last-child td{border:0}
#toast{position:fixed;left:50%;bottom:24px;z-index:50;display:flex;align-items:center;gap:10px;max-width:min(440px,calc(100vw - 32px));padding:12px 16px;border-radius:12px;background:var(--ink);color:var(--bg);font-weight:600;opacity:0;pointer-events:none;transform:translate(-50%,20px);transition:opacity .25s,transform .35s var(--e)}
#toast.show{opacity:1;transform:translate(-50%,0)}#toast.err{background:var(--bad);color:#fff}
dialog{width:min(640px,calc(100% - 24px));padding:0;border:1px solid var(--line);border-radius:16px;background:var(--panel);color:var(--ink)}
dialog[open]{animation:pop .25s var(--e)}dialog::backdrop{background:rgba(10,12,16,.55)}
@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.97)}}
.dh,.df{display:flex;align-items:center;gap:10px;padding:16px 20px}.dh{border-bottom:1px solid var(--line)}.dh h2{flex:1;margin:0;font-size:18px}
.df{justify-content:flex-end;border-top:1px solid var(--line)}.db{padding:20px}
@media(max-width:900px){.two{grid-template-columns:1fr}.cr{grid-template-columns:56px 1fr auto}.lnk{grid-column:1/-1}}
@media(max-width:760px){
.shell{grid-template-columns:1fr}
.rail{position:fixed;inset:auto 0 0;z-index:20;height:auto;flex-direction:row;padding:6px 8px calc(6px + env(safe-area-inset-bottom));border:0;border-top:1px solid var(--line)}
.brand,.who{display:none}nav{flex-direction:row;width:100%}.nb{flex:1;flex-direction:column;gap:2px;padding:7px 4px;font-size:11px}
.main{padding-bottom:100px}.top h1{font-size:22px}
.now{grid-template-columns:1fr;padding:20px 20px 0}.wave{display:none}.facts{grid-template-columns:1fr;margin:14px -20px 0}.fact{padding:12px 20px}.fact+.fact{border:0;border-top:1px solid var(--line)}
.row,.tg-grid{grid-template-columns:1fr}.bar{flex-direction:column}.bar>*{max-width:none}
.save{bottom:84px}#toast{bottom:90px}.card{padding:16px}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style>
</head>
<body class="intro">
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-home" viewBox="0 0 24 24"><path d="M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"/></symbol>
<symbol id="i-cal" viewBox="0 0 24 24"><path d="M4 6h16v14H4zM4 10h16M8 3v4M16 3v4"/></symbol>
<symbol id="i-doc" viewBox="0 0 24 24"><path d="M7 3h8l4 4v14H7zM14 3v5h5M10 13h6M10 17h6"/></symbol>
<symbol id="i-set" viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M8 15v4"/></symbol>
<symbol id="i-sun" viewBox="0 0 24 24"><path d="M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></symbol>
<symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14A8 8 0 019.5 4 8 8 0 1020 14z"/></symbol>
<symbol id="i-edit" viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16zM13 7l4 4"/></symbol>
<symbol id="i-del" viewBox="0 0 24 24"><path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13"/></symbol>
<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
<symbol id="i-eye" viewBox="0 0 24 24"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z"/></symbol>
<symbol id="i-chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></symbol>
<symbol id="i-chat" viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></symbol>
<symbol id="i-chk" viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
<symbol id="i-join" viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/></symbol>
</defs></svg>
<div class="shell">
<aside class="rail">
  <div class="brand"><span class="logo"><svg class="ic"><use href="#i-chk"/></svg></span>Attendance Bot</div>
  <nav aria-label="Main"><span class="pill" id="pill"></span>
    <button class="nb on" data-tab="overview"><svg class="ic"><use href="#i-home"/></svg>Overview</button>
    <button class="nb" data-tab="schedule"><svg class="ic"><use href="#i-cal"/></svg>Schedule</button>
    <button class="nb" data-tab="notes"><svg class="ic"><use href="#i-doc"/></svg>Notes</button>
    <button class="nb" data-tab="settings"><svg class="ic"><use href="#i-set"/></svg>Settings</button>
  </nav>
  <div class="who mut"><b id="whoName">Loading…</b><span id="whoRoll"></span></div>
</aside>
<main class="main">
<div class="top"><h1 id="title">Overview</h1><span class="sp"></span>
  <span class="chip" id="statusPill"><i></i><span>Idle</span></span>
  <button class="icb" id="themeBtn" type="button"><svg class="ic"><use id="themeUse" href="#i-moon"/></svg></button></div>

<section class="tab on" id="tab-overview">
  <div class="now rv" style="--i:0">
    <div><div class="mut">Current class</div><h2><span class="mark" id="curClass">No class right now</span></h2><div class="mut" id="nextClassHint">Checking schedule…</div></div>
    <div class="wave" id="audioWave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
    <div class="facts">
      <div class="fact"><div class="mut">Attendance</div><b id="curAtt">—</b></div>
      <div class="fact"><div class="mut">Slides captured</div><b id="curSlides">0</b></div>
      <div class="fact"><div class="mut">Last notes saved</div><b id="lastNotes">—</b></div>
    </div>
  </div>
  <div class="two rv" style="--i:1">
    <article class="card"><div class="head"><div><h2>Live captions</h2><div class="mut">Automatic captions can mishear words or names, so check unclear lines against the recording.</div></div><span class="chip bad"><i></i>Live</span></div>
      <div class="cap" id="lastCap" dir="auto">Waiting for captions…</div></article>
    <article class="card"><div class="head"><div><h2>Alerts</h2><div class="mut">Updates from the bot</div></div><span class="chip" id="alertCount">0</span></div>
      <div id="alerts"><div class="sk"></div><div class="sk"></div></div></article>
  </div>
  <article class="card rv" style="--i:2"><div class="head"><div><h2>Attendance history</h2><div class="mut">Recent sessions and outcomes</div></div></div>
    <div class="bar"><input id="historySearch" type="search" placeholder="Search by subject or date" aria-label="Search history">
      <select id="historyFilter" aria-label="Filter by status"><option value="">All statuses</option><option value="present">Marked</option><option value="joined_no_mark">Joined, not marked</option><option value="failed">Missed</option></select></div>
    <div class="tw" id="history"><div class="sk"></div><div class="sk"></div></div></article>
</section>

<section class="tab" id="tab-schedule">
  <article class="card"><div class="head"><div><h2>Join a meeting now</h2><div class="mut">Starts a one-off session. Your weekly timetable stays unchanged.</div></div></div>
    <div class="row"><div><label class="f" for="qjLink">Meeting link</label><input id="qjLink" type="url" placeholder="https://meet.google.com/…"></div>
      <div><label class="f" for="qjSubject">Class name (optional)</label><input id="qjSubject" placeholder="Quick join"></div>
      <div><label class="f" for="qjDur">Stay for (minutes)</label><input id="qjDur" type="number" value="60" min="1"></div>
      <div style="display:flex;align-items:flex-end"><button class="btn" id="joinBtn" type="button"><svg class="ic"><use href="#i-join"/></svg><span>Join now</span></button></div></div></article>
  <article class="card"><div class="head"><div><h2>Weekly timetable</h2><div class="mut">Today is outlined. A yellow edge marks your next class.</div></div>
    <button class="btn" id="addClassBtn" type="button"><svg class="ic"><use href="#i-plus"/></svg>Add class</button></div>
    <div id="scheduleList"><div class="sk"></div><div class="sk"></div><div class="sk"></div></div></article>
</section>

<section class="tab" id="tab-notes">
  <article class="card"><div class="head"><div><h2>Lecture library</h2><div class="mut">PDFs, transcripts and a study chat for each lecture.</div></div></div>
    <div class="bar"><input id="notesSearch" type="search" placeholder="Search by title or subject" aria-label="Search notes"><input id="notesDate" type="date" aria-label="Filter by date"></div>
    <div id="notesList"><div class="sk"></div><div class="sk"></div></div></article>
</section>

<section class="tab" id="tab-settings">
  <section class="acc card open"><button class="acc-h" type="button" aria-expanded="true">Profile and attendance<svg class="ic chev"><use href="#i-chev"/></svg></button><div class="acc-b"><div class="acc-i"><div class="pad">
    <div class="row"><div><label class="f" for="sName">Name</label><input id="sName"></div><div><label class="f" for="sRoll">Roll number</label><input id="sRoll"></div>
    </div>
    <label class="f" for="nameTagInput">Name spellings captions might produce</label>
    <div style="display:flex;gap:10px"><input id="nameTagInput" dir="auto" placeholder="Type a spelling and press Enter"><button class="btn ghost" id="addTagBtn" type="button">Add</button></div>
    <div class="tags" id="nameTags" aria-live="polite"></div>
    <p class="mut">Add Urdu and English spellings. The bot leaves when the meeting ends for everyone or the scheduled time is reached.</p></div></div></div></section>
  <section class="acc card open"><button class="acc-h" type="button" aria-expanded="true">Features and transcription<svg class="ic chev"><use href="#i-chev"/></svg></button><div class="acc-b"><div class="acc-i"><div class="pad">
    <div class="tg-grid">
      <label class="tog"><input type="checkbox" id="fNotes"><span class="sw"></span><span><b>Save lecture notes</b><small>Store captions and build a PDF after class.</small></span></label>
      <label class="tog"><input type="checkbox" id="fAI"><span class="sw"></span><span><b>AI study notes</b><small>Organized summaries when a provider key is set.</small></span></label>
      <label class="tog"><input type="checkbox" id="fCalled"><span class="sw"></span><span><b>Name-call alert</b><small>Sound and popup when your name or roll number is called.</small></span></label>
      <label class="tog"><input type="checkbox" id="fSlides"><span class="sw"></span><span><b>Capture slides</b><small>Save presented slides and explain them in your notes.</small></span></label>
      <label class="tog"><input type="checkbox" id="fWhisper"><span class="sw"></span><span><b>Local microphone and audio transcription</b><small>Whisper processes your default microphone and speaker playback locally; spoken questions can be answered in meeting chat.</small></span></label>
    </div>
    <div class="row" style="margin:16px 0 0">
      <div><label class="f" for="fCapLang">Teacher's caption language</label><select id="fCapLang"><option value="urdu">Urdu</option><option value="english">English</option><option value="keep">Keep Meet's setting</option></select></div>
      <div><label class="f" for="fNotesLang">AI notes language</label><select id="fNotesLang"><option>English</option><option>Urdu</option><option>Roman Urdu</option></select></div>
      <div><label class="f" for="fMode">Slide capture mode</label><select id="fMode"><option value="auto">Auto (presentations only)</option><option value="always">Always (largest video)</option><option value="off">Off</option></select></div>
      <div><label class="f" for="fInt">Check for new slide (seconds)</label><input id="fInt" type="number" min="2" max="60"></div>
      <div><label class="f" for="fKey">Snapshot interval (seconds, 0 = off)</label><input id="fKey" type="number" min="0" max="300"></div></div>
  </div></div></div></section>
  <section class="acc card"><button class="acc-h" type="button" aria-expanded="false">PDF preferences<svg class="ic chev"><use href="#i-chev"/></svg></button><div class="acc-b"><div class="acc-i"><div class="pad">
    <div class="row"><div><label class="f" for="fPdfDetail">Notes detail</label><select id="fPdfDetail"><option value="concise">Concise</option><option value="detailed">Detailed</option></select></div>
      <div><label class="f" for="fPdfPaper">Paper size</label><select id="fPdfPaper"><option value="A4">A4</option><option value="Letter">US Letter</option></select></div></div>
    <label class="tog"><input type="checkbox" id="fPdfTranscript"><span class="sw"></span><span><b>Append the full transcript to the PDF</b><small>The transcript is always saved separately too.</small></span></label>
  </div></div></div></section>
  <section class="acc card"><button class="acc-h" type="button" aria-expanded="false">AI provider<svg class="ic chev"><use href="#i-chev"/></svg></button><div class="acc-b"><div class="acc-i"><div class="pad">
    <div class="row"><div><label class="f" for="aProv">Provider</label><select id="aProv"><option value="anthropic">Anthropic (Claude)</option><option value="deepseek">DeepSeek</option><option value="gemini">Google Gemini</option></select></div>
      <div><label class="f" for="aKey">API key</label><div style="display:flex;gap:8px"><input id="aKey" type="password" autocomplete="off" placeholder="Enter a key or keep the saved one"><button class="icb" id="keyEye" type="button" aria-label="Show or hide key"><svg class="ic"><use href="#i-eye"/></svg></button></div></div>
      <div><label class="f" for="aModel">Model (optional)</label><input id="aModel"></div></div>
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap"><label class="tog" style="width:max-content"><input type="checkbox" id="aClear"><span class="sw"></span><span><b>Remove saved key</b></span></label>
      <button class="btn ghost" id="testAIButton" type="button"><span>Test connection</span></button></div>
    <p class="mut" id="aHint" role="status"></p>
  </div></div></div></section>
  <div class="save"><span class="mut">Changes apply to your next class.</span><button class="btn" id="saveSettingsButton" type="button"><svg class="ic"><use href="#i-chk"/></svg><span>Save settings</span></button></div>
</section>
</main>
</div>

<dialog id="classDialog" aria-labelledby="formTitle"><form method="dialog" onsubmit="return false">
  <div class="dh"><h2 id="formTitle">Add a class</h2><button class="icb" type="button" aria-label="Close" id="closeClass"><svg class="ic"><use href="#i-x"/></svg></button></div>
  <div class="db"><input type="hidden" id="fId"><div class="row">
    <div><label class="f" for="fDay">Day</label><select id="fDay"></select></div><div><label class="f" for="fTime">Start time</label><input id="fTime" type="time"></div>
    <div><label class="f" for="fDur">Duration (minutes)</label><input id="fDur" type="number" value="50" min="1"></div><div><label class="f" for="fSubject">Subject</label><input id="fSubject"></div>
    <div><label class="f" for="fPlat">Platform</label><select id="fPlat"><option value="meet">Google Meet</option><option value="zoom">Zoom</option></select></div>
    <div><label class="f" for="fCap">Captions language</label><select id="fCap"><option value="">Default</option><option value="urdu">Urdu</option><option value="english">English</option><option value="keep">Keep Meet's setting</option></select></div></div>
    <label class="f" for="fLink">Meeting link</label><input id="fLink" type="url" placeholder="https://…"></div>
  <div class="df"><button class="btn ghost" type="button" id="cancelClass">Cancel</button><button class="btn" type="button" id="saveClassButton"><span>Save class</span></button></div>
</form></dialog>
<dialog id="confirmDlg" style="width:min(420px,calc(100% - 24px))"><form method="dialog">
  <div class="db"><h2 id="cfTitle" style="margin:0 0 6px;font-size:18px"></h2><p class="mut" id="cfMsg" style="margin:0"></p></div>
  <div class="df"><button class="btn ghost" value="no">Cancel</button><button class="btn danger" value="ok" id="cfOk">Delete</button></div>
</form></dialog>
<div id="toast" role="status" aria-live="polite"></div>
<script>
const DAYS=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
let CFG=null,HISTORY=[],NOTES=[],NAME_TAGS=[],OPEN=new Set(),OPENED=false,LASTCAP="";
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ic=n=>`<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const junk=/\b(?:thank\s+(?:you|u)\s+for\s+watching|thanks?\s+for\s+watching|please\s+subscribe|like\s+and\s+subscribe|subscribe\s+to\s+(?:my|the|this)\s+channel|see\s+you\s+in\s+the\s+next\s+video)\b/i;

function toast(msg,err=false){const t=$("toast");t.textContent=msg;t.className=err?"err":"";requestAnimationFrame(()=>t.classList.add("show"));
  clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove("show"),err?6000:2800);}
async function api(method,url,body){
  const o={method,headers:{}};if(body!==undefined){o.headers["Content-Type"]="application/json";o.body=JSON.stringify(body);}
  let r;try{r=await fetch(url,o);}catch(e){toast("The bot is not reachable. Check that it is running.",true);throw e;}
  let d={};try{d=await r.json();}catch(e){}
  if(!r.ok){toast(d.error||"Request failed ("+r.status+")",true);throw new Error(d.error||r.status);}return d;}
const noteUrl=(f,file)=>"/notes/"+String(f||"").split("/").map(encodeURIComponent).join("/")+"/"+file;
function busy(b,on,label){b.disabled=on;b.classList.toggle("busy",on);const s=b.querySelector("span");if(s&&label)s.textContent=label;}
function confirmBox(title,msg,ok){return new Promise(res=>{const d=$("confirmDlg");$("cfTitle").textContent=title;$("cfMsg").textContent=msg;$("cfOk").textContent=ok;
  d.returnValue="no";d.addEventListener("close",()=>res(d.returnValue==="ok"),{once:true});d.showModal();});}
function countTo(el,to){const from=+el.dataset.v||0;el.dataset.v=to;if(from===to){el.textContent=to;return;}
  const t0=performance.now();(function f(t){const p=Math.min(1,(t-t0)/600);el.textContent=Math.round(from+(to-from)*(1-Math.pow(1-p,3)));if(p<1)requestAnimationFrame(f);})(t0);}

/* theme */
function setTheme(t,spin){document.documentElement.dataset.theme=t;try{localStorage.setItem("attendance-theme",t);}catch(e){}
  $("themeUse").setAttribute("href",t==="dark"?"#i-sun":"#i-moon");$("themeBtn").setAttribute("aria-label",t==="dark"?"Switch to light theme":"Switch to dark theme");
  if(spin){$("themeBtn").classList.add("spin");setTimeout(()=>$("themeBtn").classList.remove("spin"),500);}}
$("themeBtn").onclick=()=>setTheme(document.documentElement.dataset.theme==="dark"?"light":"dark",true);
let saved=null;try{saved=localStorage.getItem("attendance-theme");}catch(e){}
setTheme(saved||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"));

/* navigation */
function placePill(){const b=document.querySelector(".nb.on"),p=$("pill");p.style.width=b.offsetWidth+"px";p.style.height=b.offsetHeight+"px";
  p.style.transform="translate("+b.offsetLeft+"px,"+b.offsetTop+"px)";}
function go(tab){const b=document.querySelector('.nb[data-tab="'+tab+'"]')||document.querySelector(".nb");tab=b.dataset.tab;
  document.querySelectorAll(".nb").forEach(x=>x.classList.toggle("on",x===b));
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("on",t.id==="tab-"+tab));
  $("title").textContent=b.textContent.trim();placePill();history.replaceState(null,"","#"+tab);if(tab==="notes")loadNotes();}
document.querySelectorAll(".nb").forEach(b=>b.onclick=()=>go(b.dataset.tab));
addEventListener("resize",placePill);
document.addEventListener("click",e=>{const h=e.target.closest(".acc-h");if(!h)return;const a=h.parentElement,o=a.classList.toggle("open");
  h.setAttribute("aria-expanded",o);if(a.dataset.day){o?OPEN.add(a.dataset.day):OPEN.delete(a.dataset.day);}});

/* schedule */
function nextClass(){if(!CFG)return null;const n=new Date(),di=(n.getDay()+6)%7,mi=n.getHours()*60+n.getMinutes();let best=null,bd=Infinity;
  (CFG.classes||[]).forEach(c=>{const d=DAYS.indexOf(c.day);if(d<0)return;const[h,m]=String(c.time||"0:0").split(":").map(Number);
    let x=((d-di+7)%7)*1440+h*60+m-mi;if(x<0)x+=10080;if(x<bd){bd=x;best=c;}});return best;}
async function loadConfig(){CFG=await api("GET","/api/config");$("whoName").textContent=CFG.student.name||"Student";$("whoRoll").textContent=CFG.student.roll_no||"No roll number";
  renderClasses();fillSettings();const nx=nextClass();$("nextClassHint").textContent=nx?"Next: "+nx.subject+", "+nx.day+" at "+nx.time:"No classes scheduled";}
function renderClasses(){
  const cl=CFG.classes||[],today=DAYS[(new Date().getDay()+6)%7],nx=nextClass();
  if(!OPENED){OPEN.add(today);OPENED=true;}
  $("scheduleList").innerHTML=DAYS.map(day=>{
    const list=cl.filter(c=>c.day===day).sort((a,b)=>String(a.time).localeCompare(String(b.time)));if(!list.length)return"";
    const t=day===today,o=OPEN.has(day);
    return`<section class="acc day ${t?"today":""} ${o?"open":""}" data-day="${day}"><button class="acc-h" type="button" aria-expanded="${o}">${day}
      ${t?'<span class="chip acc">Today</span>':""}<span class="mut">${list.length} ${list.length===1?"class":"classes"}</span><svg class="ic chev"><use href="#i-chev"/></svg></button>
      <div class="acc-b"><div class="acc-i"><div class="pad">${list.map(c=>`<div class="cr ${nx&&c.id===nx.id?"next":""}">
        <div class="mono">${esc(c.time)}</div>
        <div><div class="ct">${esc(c.subject)}${c._test?'<span class="chip warn">Test</span>':""}${c.once?'<span class="chip acc">One-off</span>':""}</div>
          <div class="mut">${esc(c.duration)} min · ${c.platform==="zoom"?"Zoom":"Meet"} · ${c.captions?esc(c.captions)+" captions":"default captions"}</div></div>
        <div class="lnk"><input class="mono ${c.link?"":"miss"}" aria-label="Meeting link for ${esc(c.subject)}" value="${esc(c.link||"")}" placeholder="Paste meeting link" data-id="${esc(c.id)}"></div>
        <div class="acts"><button class="icb" type="button" aria-label="Edit ${esc(c.subject)}" data-edit="${esc(c.id)}">${ic("edit")}</button>
          <button class="icb bad" type="button" aria-label="Delete ${esc(c.subject)}" data-del="${esc(c.id)}">${ic("del")}</button></div></div>`).join("")}</div></div></div></section>`;
  }).join("")||'<div class="empty"><b>No classes yet</b>Use Add class to build your weekly timetable.</div>';}
$("scheduleList").addEventListener("change",e=>{if(e.target.dataset.id)setLink(e.target.dataset.id,e.target);});
$("scheduleList").addEventListener("click",e=>{const b=e.target.closest("[data-edit],[data-del]");if(!b)return;b.dataset.edit?editClass(b.dataset.edit):deleteClass(b.dataset.del);});
async function setLink(id,input){const c=CFG.classes.find(x=>x.id===id);if(!c)return;
  const body={day:c.day,time:c.time,duration:c.duration,subject:c.subject,platform:c.platform,link:input.value.trim(),captions:c.captions||""};
  if(/zoom\.us/i.test(body.link))body.platform="zoom";else if(/meet\.google\.com/i.test(body.link))body.platform="meet";
  try{await api("PUT","/api/classes/"+encodeURIComponent(id),body);toast("Meeting link saved");await loadConfig();}catch(e){input.focus();}}
function resetForm(){["fId","fSubject","fLink","fTime"].forEach(i=>$(i).value="");$("fDur").value=50;$("fPlat").value="meet";$("fCap").value="";$("formTitle").textContent="Add a class";}
$("addClassBtn").onclick=()=>{resetForm();$("classDialog").showModal();};
const closeClass=()=>$("classDialog").close();$("closeClass").onclick=closeClass;$("cancelClass").onclick=closeClass;
function editClass(id){const c=CFG.classes.find(x=>x.id===id);if(!c)return;
  $("fId").value=id;$("fDay").value=c.day;$("fTime").value=c.time;$("fDur").value=c.duration;$("fSubject").value=c.subject;
  $("fPlat").value=c.platform;$("fLink").value=c.link||"";$("fCap").value=c.captions||"";$("formTitle").textContent="Edit "+c.subject;$("classDialog").showModal();}
$("saveClassButton").onclick=async()=>{const b=$("saveClassButton");busy(b,true,"Saving");
  const body={day:$("fDay").value,time:$("fTime").value,duration:$("fDur").value,subject:$("fSubject").value,platform:$("fPlat").value,link:$("fLink").value,captions:$("fCap").value},id=$("fId").value;
  try{id?await api("PUT","/api/classes/"+encodeURIComponent(id),body):await api("POST","/api/classes",body);toast("Class saved");closeClass();await loadConfig();}
  catch(e){}finally{busy(b,false,"Save class");}};
async function deleteClass(id){const c=CFG.classes.find(x=>x.id===id);
  if(!await confirmBox("Delete this class?",c?c.subject+" on "+c.day+" at "+c.time+" will be removed.":"It will be removed.","Delete class"))return;
  try{await api("DELETE","/api/classes/"+encodeURIComponent(id));toast("Class deleted");await loadConfig();}catch(e){}}
$("joinBtn").onclick=async()=>{const b=$("joinBtn");busy(b,true,"Joining");
  try{await api("POST","/api/quickjoin",{link:$("qjLink").value,subject:$("qjSubject").value,duration:$("qjDur").value});
    toast("Queued. The bot will join in a few seconds.");$("qjLink").value="";await loadConfig();}catch(e){}finally{busy(b,false,"Join now");}};

/* settings */
function renderTags(){$("nameTags").innerHTML=NAME_TAGS.map((n,i)=>`<span class="tag" dir="auto">${esc(n)}<button type="button" aria-label="Remove ${esc(n)}" data-rm="${i}">${ic("x")}</button></span>`).join("");}
function addTag(){const f=$("nameTagInput"),v=f.value.trim();if(v&&!NAME_TAGS.includes(v)){NAME_TAGS.push(v);renderTags();}f.value="";}
$("addTagBtn").onclick=addTag;$("nameTagInput").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();addTag();}});
$("nameTags").addEventListener("click",e=>{const b=e.target.closest("[data-rm]");if(b){NAME_TAGS.splice(+b.dataset.rm,1);renderTags();}});
const FT=[["fNotes","notes"],["fAI","ai_summary"],["fCalled","called_alert"],["fSlides","slides"],["fWhisper","whisper_transcription"]];
function fillSettings(){const s=CFG.student,f=CFG.features;
  $("sName").value=s.name||"";$("sRoll").value=s.roll_no||"";NAME_TAGS=[...(s.urdu_names||[])];renderTags();
  FT.forEach(([id,k])=>$(id).checked=!!f[k]);
  $("fMode").value=f.slide_mode;$("fInt").value=f.slide_interval;$("fCapLang").value=f.caption_language;$("fNotesLang").value=f.notes_language;
  $("fKey").value=f.keyframe_interval;$("fPdfDetail").value=f.pdf_detail;$("fPdfPaper").value=f.pdf_paper_size;$("fPdfTranscript").checked=f.pdf_include_transcript;
  $("aProv").value=CFG.ai.provider;showProv();}
function showProv(){const p=CFG.ai.providers[$("aProv").value];$("aModel").value=p.model||"";$("aModel").placeholder=p.default_model;
  $("aKey").value="";$("aClear").checked=false;$("aClear").disabled=!p.has_key;
  $("aHint").textContent=p.has_key?"A "+p.label+" key is saved ("+p.key_hint+"). Leave the field empty to keep it.":"No "+p.label+" key saved yet.";}
$("aProv").onchange=showProv;$("keyEye").onclick=()=>{$("aKey").type=$("aKey").type==="password"?"text":"password";};
$("testAIButton").onclick=async()=>{const b=$("testAIButton");busy(b,true,"Testing");
  try{await api("POST","/api/ai/test",{provider:$("aProv").value,api_key:$("aKey").value,model:$("aModel").value});toast("Connected. The provider replied.");}
  catch(e){}finally{busy(b,false,"Test connection");}};
$("saveSettingsButton").onclick=async()=>{const b=$("saveSettingsButton");busy(b,true,"Saving");
  const body={student:{name:$("sName").value,roll_no:$("sRoll").value,urdu_names:NAME_TAGS},
    features:{notes:$("fNotes").checked,ai_summary:$("fAI").checked,called_alert:$("fCalled").checked,whisper_transcription:$("fWhisper").checked,slides:$("fSlides").checked,
      slide_mode:$("fMode").value,slide_interval:$("fInt").value,caption_language:$("fCapLang").value,notes_language:$("fNotesLang").value,keyframe_interval:$("fKey").value,
      pdf_detail:$("fPdfDetail").value,pdf_paper_size:$("fPdfPaper").value,pdf_include_transcript:$("fPdfTranscript").checked},
    ai:{provider:$("aProv").value,model:$("aModel").value,api_key:$("aKey").value,clear_key:$("aClear").checked}};
  try{await api("POST","/api/settings",body);toast("Settings saved");await loadConfig();}catch(e){}finally{busy(b,false,"Save settings");}};

/* notes */
async function loadNotes(){$("notesList").innerHTML='<div class="sk"></div><div class="sk"></div>';
  try{NOTES=await api("GET","/api/notes");renderNotes();}catch(e){$("notesList").innerHTML='<div class="empty"><b>Notes could not be loaded</b>Check that the bot is running, then open this tab again.</div>';}}
function renderNotes(){
  const q=$("notesSearch").value.trim().toLowerCase(),d=$("notesDate").value;
  const list=NOTES.filter(n=>(!q||[n.lecture_title,n.subject].some(v=>String(v||"").toLowerCase().includes(q)))&&(!d||n.date===d));
  const g=new Map();list.forEach(n=>{const k=String(n.subject||"").toLowerCase()==="quick join"?"Quick join sessions":(n.lecture_title||n.subject||"Lecture");(g.get(k)||g.set(k,[]).get(k)).push(n);});
  $("notesList").innerHTML=list.length?[...g].map(([name,items])=>(items.length>1?`<div class="gh">${esc(name)}<span class="chip">${items.length} sessions</span></div>`:"")+
    items.map(n=>`<article class="nr"><div class="ni"><b>${esc(n.lecture_title||n.subject||"Lecture")}</b><span class="mut">${esc(n.subject||"")} · <span class="mono">${esc(n.date||"")} ${esc(n.time||"")}</span>${n.slides?" · "+n.slides+" slides":""}</span></div>
      <span class="chip ${n.done?"ok":"warn"}">${n.done?"Ready":"In progress"}</span>
      <div class="nl">${n.pdf?`<a href="${noteUrl(n.folder,"notes.pdf")}" target="_blank" rel="noopener">${ic("doc")}PDF</a>`:(n.html?`<a href="${noteUrl(n.folder,"notes.html")}" target="_blank" rel="noopener">${ic("doc")}Notes</a>`:"")}
        ${(n.pdf||n.html)&&n.done?`<a href="${noteUrl(n.folder,"study")}" target="_blank" rel="noopener">${ic("chat")}Study chat</a>`:""}
        <a href="${noteUrl(n.folder,"transcript.md")}" target="_blank" rel="noopener">Transcript</a>
        ${n.corrected_transcript?`<a href="${noteUrl(n.folder,"transcript_corrected.md")}" target="_blank" rel="noopener">Corrected</a>`:""}</div>${n.done?"":'<span class="prog"></span>'}</article>`).join("")).join("")
    :'<div class="empty"><b>No matching notes</b>Finished lectures will appear here.</div>';}
$("notesSearch").oninput=renderNotes;$("notesDate").onchange=renderNotes;

/* live state */
const ST={joining:"Joining",in_class:"In class",generating_notes:"Making notes",waiting:"Waiting",idle:"Idle"};
async function pollState(){
  try{const s=await api("GET","/api/state"),st=s.status||"idle",c=s.current_class;
    $("statusPill").className="chip s-"+st;$("statusPill").innerHTML="<i></i><span>"+esc(ST[st]||st)+"</span>";
    const name=c?c.subject:"No class right now",m=$("curClass");
    if(m.textContent!==name||m.classList.contains("on")!==!!c){m.textContent=name;m.classList.remove("on");void m.offsetWidth;if(c)m.classList.add("on");}
    $("curAtt").textContent=c?(s.attendance_marked?"Marked":"Not marked yet"):"—";
    countTo($("curSlides"),Number(s.slide_count||0));$("lastNotes").textContent=s.last_notes||"—";
    const cap=String(s.last_caption||""),txt=junk.test(cap)?"Hidden: this line looks like a video outro, not lecture speech.":(cap||"Waiting for captions…");
    if(txt!==LASTCAP){LASTCAP=txt;const el=$("lastCap");el.textContent=txt;el.classList.remove("new");void el.offsetWidth;el.classList.add("new");}
    $("audioWave").classList.toggle("on",st==="in_class");
    const al=(s.alerts||[]).slice().reverse();$("alertCount").textContent=al.length;
    $("alerts").innerHTML=al.length?al.map(a=>`<div class="al ${esc(a.kind)}"><b class="mono">${esc(a.time)}</b> ${esc(a.subject)}: ${esc(a.text)}</div>`).join(""):'<div class="empty"><b>All quiet</b>Alerts will show up here.</div>';
  }catch(e){$("statusPill").className="chip s-offline";$("statusPill").innerHTML="<i></i><span>Offline</span>";}}
function renderHistory(){
  const q=$("historySearch").value.trim().toLowerCase(),f=$("historyFilter").value;
  const rows=HISTORY.filter(e=>(!q||[e.subject,e.timestamp].some(v=>String(v||"").toLowerCase().includes(q)))&&(!f||e.status===f));
  $("history").innerHTML=rows.length?`<table><thead><tr><th>Date</th><th>Time</th><th>Subject</th><th>Platform</th><th>Attendance</th></tr></thead><tbody>${rows.map(e=>{
    const k=e.status==="present"?["ok","Marked"]:e.status==="joined_no_mark"?["warn","Joined, not marked"]:["bad","Missed"],t=e.timestamp||"";
    return`<tr><td class="mono">${esc(t.slice(0,10))}</td><td class="mono">${esc(t.slice(11,16))}</td><td>${esc(e.subject)}</td><td>${esc(e.platform||"")}</td><td><span class="chip ${k[0]}">${k[1]}</span></td></tr>`;}).join("")}</tbody></table>`
    :'<div class="empty"><b>No sessions found</b>Try a different search or filter.</div>';}
async function loadHistory(){try{HISTORY=await api("GET","/api/history");renderHistory();}catch(e){$("history").innerHTML='<div class="empty">History could not be loaded.</div>';}}
$("historySearch").oninput=renderHistory;$("historyFilter").onchange=renderHistory;

/* boot */
DAYS.forEach(d=>$("fDay").add(new Option(d,d)));
go((location.hash||"#overview").slice(1));requestAnimationFrame(()=>requestAnimationFrame(()=>$("pill").classList.add("ready")));
(document.fonts?document.fonts.ready:Promise.resolve()).then(placePill);
setTimeout(()=>document.body.classList.remove("intro"),1400);
loadConfig().catch(()=>toast("Could not load settings. Check the bot logs.",true));
pollState();loadHistory();setInterval(pollState,3000);setInterval(loadHistory,30000);
</script>
</body>
</html>
"""