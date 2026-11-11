"""PDF viewer and study chat using lecture context plus general knowledge."""

import html
import json

_TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>__SUBJECT__ — Study notes</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#f3f4f6;--panel:#fff;--sunk:#eceef2;--line:#dde1e8;--ink:#14181f;--mute:#586170;--acc:#2447d6;--mark:#ffe14d;--bad:#c0392b;--e:cubic-bezier(.2,.7,.2,1);color-scheme:light}
[data-theme=dark]{--bg:#0e1116;--panel:#161a21;--sunk:#1d222b;--line:#272d38;--ink:#e9ecf2;--mute:#9aa3b2;--acc:#8ba6ff;--mark:#6b5a0f;--bad:#ff8a7a;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Inter,"Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
button,textarea{font:inherit;color:inherit}button{cursor:pointer}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.ic{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
header{display:flex;align-items:center;gap:14px;height:60px;padding:0 20px;border-bottom:1px solid var(--line);background:var(--panel)}
header a{display:inline-flex;align-items:center;gap:6px;color:var(--mute);font-weight:600;text-decoration:none;transition:color .2s}
header a:hover{color:var(--ink)}
.title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:16px;font-weight:700;letter-spacing:-.01em}
.icb{display:inline-grid;place-items:center;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel);transition:background .2s,transform .12s}
.icb:hover{background:var(--sunk)}.icb:active{transform:scale(.92)}
main{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.85fr);height:calc(100vh - 60px)}
iframe{width:100%;height:100%;border:0;background:#fff}
aside{display:flex;flex-direction:column;min-width:0;min-height:0;border-left:1px solid var(--line);background:var(--panel)}
.intro{padding:16px 20px;border-bottom:1px solid var(--line)}.intro b{display:block;font-size:16px}.intro span{color:var(--mute);font-size:13px}
#messages{flex:1;min-height:0;overflow:auto;padding:20px 18px;scroll-behavior:smooth}
.welcome{max-width:440px;margin:12px auto}.welcome h2{margin:0 0 4px;font-size:22px;letter-spacing:-.02em}.welcome p{margin:0 0 16px;color:var(--mute)}
.sg{display:grid;gap:8px}
.sg button{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border:1px solid var(--line);border-radius:11px;background:var(--panel);text-align:left;font-weight:600;transition:border-color .2s,background .2s,transform .15s var(--e)}
.sg button:hover{border-color:var(--acc);background:var(--sunk);transform:translateX(3px)}.sg .ic{color:var(--mute)}
.msg{display:flex;margin:0 auto 22px;max-width:760px;animation:in .35s var(--e)}
@keyframes in{from{opacity:0;transform:translateY(8px)}}
.msg.user{justify-content:flex-end}
.msg.user .bubble{max-width:85%;padding:10px 15px;border-radius:16px 16px 4px 16px;background:var(--ink);color:var(--bg);overflow-wrap:anywhere}
.msg.assistant{gap:12px}
.av{display:grid;place-items:center;flex:none;width:30px;height:30px;margin-top:2px;border-radius:9px;background:var(--mark);color:var(--ink)}
.msg.assistant .bubble{flex:1;min-width:0;overflow-wrap:anywhere}
.answer{line-height:1.7}.answer>:first-child{margin-top:0}.answer>:last-child{margin-bottom:0}
.answer h1,.answer h2,.answer h3{margin:16px 0 6px;line-height:1.3;letter-spacing:-.01em}
.answer h1{font-size:19px}.answer h2{font-size:17px}.answer h3{font-size:15px}
.answer p{margin:8px 0}.answer ul,.answer ol{margin:8px 0;padding-left:22px}.answer li{margin:4px 0}.answer li::marker{color:var(--acc)}
.answer code{padding:2px 6px;border-radius:5px;background:var(--sunk);font-family:"IBM Plex Mono",Consolas,monospace;font-size:13px}
.answer pre{overflow:auto;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--sunk)}.answer pre code{padding:0;background:none}
.answer table{display:block;overflow:auto;border-collapse:collapse;margin:10px 0;font-size:14px}
.answer th,.answer td{padding:7px 11px;border:1px solid var(--line);text-align:left;vertical-align:top}.answer th{background:var(--sunk)}
.answer blockquote{margin:10px 0;padding:2px 0 2px 14px;border-left:3px solid var(--mark);color:var(--mute)}
.answer a{color:var(--acc)}
.cite{display:inline-block;margin:0 2px;padding:0 6px;border-radius:5px;background:var(--sunk);color:var(--acc);font:500 12px "IBM Plex Mono",Consolas,monospace}
.acts{display:flex;gap:4px;margin-top:8px}
.act{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:0;border-radius:7px;background:none;color:var(--mute);font-size:13px;transition:background .2s,color .2s}
.act:hover,.act[aria-pressed=true]{background:var(--sunk);color:var(--ink)}
.dots{display:flex;gap:5px;padding:10px 2px}.dots i{width:7px;height:7px;border-radius:50%;background:var(--mute);animation:hop 1s ease-in-out infinite}
.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}
@keyframes hop{0%,60%,100%{transform:none;opacity:.4}30%{transform:translateY(-5px);opacity:1}}
.err{min-height:0;padding:0 20px;color:var(--bad);font-size:14px}.err:not(:empty){padding:8px 20px;animation:in .3s var(--e)}
.chips{display:flex;gap:8px;overflow-x:auto;padding:10px 18px 4px}
.chip{flex:none;padding:6px 12px;border:1px solid var(--line);border-radius:99px;background:var(--panel);font-size:13px;font-weight:600;transition:background .2s,border-color .2s,transform .12s}
.chip:hover{background:var(--sunk);border-color:var(--mute)}.chip:active{transform:scale(.95)}
form{padding:8px 16px 14px}
.composer{display:flex;align-items:flex-end;gap:8px;max-width:760px;margin:auto;padding:8px;border:1px solid var(--line);border-radius:14px;background:var(--panel);transition:border-color .2s}
.composer:focus-within{border-color:var(--acc)}
textarea{flex:1;min-height:40px;max-height:140px;padding:9px;border:0;outline:0;resize:none;background:none;line-height:1.5}
textarea::placeholder{color:var(--mute)}
.send{display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:10px;background:var(--ink);color:var(--bg);transition:transform .12s,opacity .2s}
.send:hover{opacity:.88}.send:active{transform:scale(.92)}.send:disabled{opacity:.4;cursor:wait}
.hint{max-width:760px;margin:6px auto 0;color:var(--mute);font-size:12px}
@media(max-width:800px){main{grid-template-columns:1fr;grid-template-rows:42vh minmax(480px,1fr);height:auto;min-height:calc(100vh - 60px)}aside{border-left:0;border-top:1px solid var(--line)}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}

:root,[data-theme=light]{--bg:#faf9f5;--panel:#fff;--sunk:#f0eee6;--line:#e6e3d9;--ink:#1f1e1d;--mute:#73726c;--acc:#d97757;--mark:#f5e1a4}
[data-theme=dark]{--bg:#262624;--panel:#1f1e1d;--sunk:#30302e;--line:rgba(255,255,255,.09);--ink:#faf9f5;--mute:#9c9a92;--acc:#d97757;--mark:#5c4a1f}
h1,h2,.brand,.top h1{font-family:'Source Serif 4',Georgia,serif;font-weight:500}
.rail{background:var(--panel)}.logo{background:var(--acc);color:#fff;border-radius:50%}
button,input,select,textarea{border-radius:12px}
textarea,input[type=text],input[type=password],select{background:var(--sunk);border:1px solid var(--line)}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-back" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></symbol>
<symbol id="i-ext" viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/></symbol>
<symbol id="i-sun" viewBox="0 0 24 24"><path d="M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></symbol>
<symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14A8 8 0 019.5 4 8 8 0 1020 14z"/></symbol>
<symbol id="i-up" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></symbol>
<symbol id="i-arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
<symbol id="i-copy" viewBox="0 0 24 24"><path d="M9 9h11v11H9zM5 15V4h11"/></symbol>
<symbol id="i-chk" viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></symbol>
<symbol id="i-up2" viewBox="0 0 24 24"><path d="M7 11v9H4v-9zM7 11l4-8c2 0 3 1 3 3v3h6l-2 9H7"/></symbol>
<symbol id="i-down" viewBox="0 0 24 24"><path d="M7 13V4H4v9zM7 13l4 8c2 0 3-1 3-3v-3h6l-2-9H7"/></symbol>
<symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/></symbol>
</defs></svg>
<header><a href="/"><svg class="ic"><use href="#i-back"/></svg>Dashboard</a><span class="title">__SUBJECT__</span>
  <a id="openFile" target="_blank" rel="noopener">Open file<svg class="ic"><use href="#i-ext"/></svg></a>
  <button class="icb" id="themeBtn" type="button"><svg class="ic"><use id="themeUse" href="#i-moon"/></svg></button></header>
<main>
<iframe id="pdf" title="Lecture notes"></iframe>
<aside>
  <div class="intro"><b>Study chat</b><span>Answers use lecture notes when relevant and general knowledge when they are not enough.</span></div>
  <div id="messages" aria-live="polite">
    <div id="welcome" class="welcome">
      <h2>What would you like to review?</h2>
      <p>Ask anything about this lecture, or start with one of these.</p>
      <div class="sg">
        <button data-prompt="What are the main topics in this lecture?">What topics did we cover?<svg class="ic"><use href="#i-arrow"/></svg></button>
        <button data-prompt="Explain the most important concept simply, with an example.">Explain the most important concept<svg class="ic"><use href="#i-arrow"/></svg></button>
        <button data-prompt="What should I remember for the exam?">What should I remember for the exam?<svg class="ic"><use href="#i-arrow"/></svg></button>
        <button data-prompt="Create a 5-question quiz with answers from this lecture.">Quiz me on this lecture<svg class="ic"><use href="#i-arrow"/></svg></button>
      </div>
    </div>
  </div>
  <div id="error" class="err" role="alert"></div>
  <nav class="chips" aria-label="Quick prompts">
    <button class="chip" data-prompt="Summarize the main ideas from this lecture.">Summarize</button>
    <button class="chip" data-prompt="List the topics covered in this lecture as bullets.">List topics</button>
    <button class="chip" data-prompt="Make me a short quiz from this lecture.">Quiz me</button>
    <button class="chip" data-prompt="Explain the main concept simply, with a concrete example.">Explain simply</button>
    <button class="chip" data-prompt="List the key terms and define each one.">Key terms</button>
  </nav>
  <form id="form">
    <div class="composer"><textarea id="question" maxlength="1000" rows="1" placeholder="Ask about this lecture…" aria-label="Your question" required></textarea>
      <button id="send" class="send" type="submit" aria-label="Send message"><svg class="ic"><use href="#i-up"/></svg></button></div>
    <div class="hint">Enter to send, Shift+Enter for a new line.</div>
  </form>
</aside>
</main>
<script>
const folder = __FOLDER__;
const documentName = __DOCUMENT__;
const base = folder.split("/").map(encodeURIComponent).join("/");
const fileUrl = "/notes/" + base + "/" + encodeURIComponent(documentName);
const $ = id => document.getElementById(id);
$("pdf").src = fileUrl; $("openFile").href = fileUrl;
const messages = $("messages"), form = $("form"), input = $("question"), send = $("send"), error = $("error");
const history = [];
const ic = n => '<svg class="ic" aria-hidden="true"><use href="#i-' + n + '"/></svg>';

function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("attendance-theme", t); } catch (e) {}
  $("themeUse").setAttribute("href", t === "dark" ? "#i-sun" : "#i-moon");
  $("themeBtn").setAttribute("aria-label", t === "dark" ? "Switch to light theme" : "Switch to dark theme");
}
$("themeBtn").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
let saved = null; try { saved = localStorage.getItem("attendance-theme"); } catch (e) {}
setTheme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
}
function inlineMarkdown(text) {
  let v = escapeHtml(text);
  v = v.replace(/`([^`]+)`/g, "<code>$1</code>");
  v = v.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  v = v.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  v = v.replace(/\[([^\]]+)\]\((https:\/\/[^ )]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return v.replace(/\[(\d{2}:\d{2}(?::\d{2})?)\]/g, '<span class="cite">$1</span>');
}
function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r/g, "").split("\n"), out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.startsWith("```")) {
      const block = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) block.push(lines[i++]);
      if (i < lines.length) i++;
      out.push("<pre><code>" + escapeHtml(block.join("\n")) + "</code></pre>"); continue;
    }
    if (/^\s*\|?.+\|.+\|?\s*$/.test(line) && i + 1 < lines.length &&
        /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i + 1])) {
      const cells = row => row.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const heads = cells(line); i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      out.push("<table><thead><tr>" + heads.map(c => "<th>" + inlineMarkdown(c) + "</th>").join("") + "</tr></thead><tbody>" +
        rows.map(r => "<tr>" + heads.map((_, k) => "<td>" + inlineMarkdown(r[k] || "") + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.+)$/);
    if (h) { out.push("<h" + h[1].length + ">" + inlineMarkdown(h[2]) + "</h" + h[1].length + ">"); i++; continue; }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) items.push("<li>" + inlineMarkdown(lines[i++].replace(/^\s*[-*+]\s+/, "")) + "</li>");
      out.push("<ul>" + items.join("") + "</ul>"); continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push("<li>" + inlineMarkdown(lines[i++].replace(/^\s*\d+[.)]\s+/, "")) + "</li>");
      out.push("<ol>" + items.join("") + "</ol>"); continue;
    }
    if (/^>\s?/.test(line)) { out.push("<blockquote>" + inlineMarkdown(line.replace(/^>\s?/, "")) + "</blockquote>"); i++; continue; }
    const para = [line.trim()]; i++;
    while (i < lines.length && lines[i].trim() && !/^(#{1,3})\s|^```|^\s*[-*+]\s+|^\s*\d+[.)]\s+|^>\s?/.test(lines[i])) para.push(lines[i++].trim());
    out.push("<p>" + inlineMarkdown(para.join(" ")) + "</p>");
  }
  return out.join("");
}
const toEnd = () => { messages.scrollTop = messages.scrollHeight; };
function addMessage(role, content) {
  const w = $("welcome"); if (w) w.remove();
  const row = document.createElement("div"); row.className = "msg " + role;
  if (role === "assistant") {
    row.innerHTML = '<div class="av" aria-hidden="true">' + ic("spark") + '</div>';
    const bubble = document.createElement("div"); bubble.className = "bubble";
    bubble.innerHTML = '<div class="answer">' + renderMarkdown(content) + '</div><div class="acts"></div>';
    const acts = bubble.querySelector(".acts");
    const copy = document.createElement("button"); copy.className = "act"; copy.type = "button"; copy.setAttribute("aria-label", "Copy answer");
    copy.innerHTML = ic("copy") + "<span>Copy</span>";
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(content); copy.innerHTML = ic("chk") + "<span>Copied</span>"; }
      catch (e) { copy.querySelector("span").textContent = "Select text to copy"; }
      setTimeout(() => { copy.innerHTML = ic("copy") + "<span>Copy</span>"; }, 1800);
    };
    acts.appendChild(copy);
    for (const [label, icon] of [["Helpful", "up2"], ["Not helpful", "down"]]) {
      const b = document.createElement("button"); b.className = "act"; b.type = "button"; b.title = label;
      b.setAttribute("aria-label", label); b.setAttribute("aria-pressed", "false"); b.innerHTML = ic(icon);
      b.onclick = () => { acts.querySelectorAll("[aria-pressed]").forEach(x => x.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); };
      acts.appendChild(b);
    }
    row.appendChild(bubble);
  } else {
    const bubble = document.createElement("div"); bubble.className = "bubble"; bubble.textContent = content; row.appendChild(bubble);
  }
  messages.appendChild(row); toEnd();
}
function addLoading() {
  const row = document.createElement("div"); row.className = "msg assistant"; row.id = "typing";
  row.innerHTML = '<div class="av" aria-hidden="true">' + ic("spark") + '</div><div class="bubble"><div class="dots" role="status" aria-label="Thinking"><i></i><i></i><i></i></div></div>';
  messages.appendChild(row); toEnd();
}
function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
async function ask(question) {
  question = question.trim();
  if (!question || send.disabled) return;
  input.value = ""; autoGrow(); error.textContent = "";
  addMessage("user", question); send.disabled = true; addLoading();
  try {
    const r = await fetch("/api/notes/" + base + "/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question, history: history.slice(-6)})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Could not get an answer.");
    $("typing")?.remove(); addMessage("assistant", data.answer);
    history.push({role: "user", content: question}, {role: "assistant", content: data.answer});
  } catch (e) {
    $("typing")?.remove(); error.textContent = e.message || "Could not reach the study assistant. Check that the bot is running.";
  } finally { send.disabled = false; input.focus(); }
}
form.addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
input.addEventListener("input", autoGrow);
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll("[data-prompt]").forEach(b => b.addEventListener("click", () => ask(b.dataset.prompt)));
</script>
</body>
</html>"""


def render(folder: str, subject: str, document: str) -> str:
    def js(value: str) -> str:
        return json.dumps(value).replace("<", "\\u003c")

    return (
        _TEMPLATE.replace("__SUBJECT__", html.escape(subject))
        .replace("__FOLDER__", js(folder))
        .replace("__DOCUMENT__", js(document))
    )