"""PDF viewer and lecture-grounded study chat page."""

import html
import json


def render(folder: str, subject: str, document: str) -> str:
    folder_json = json.dumps(folder).replace("<", "\\u003c")
    document_json = json.dumps(document).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)} — Study notes</title>
<style>
:root {{ color-scheme:dark; --bg:#090b12; --panel:#10131d; --line:#242a39; --muted:#a4adc0; --text:#edf1fa; --accent:#a78bfa; --user:#332968 }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.55 'Segoe UI',system-ui,sans-serif }}
header {{ height:60px; display:flex; align-items:center; gap:16px; padding:0 20px; border-bottom:1px solid var(--line); background:#0d0f17 }}
a {{ color:#a5d8ff; text-decoration:none }} a:hover {{ text-decoration:underline }}
.title {{ font-weight:750; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }} .grow {{ flex:1 }}
main {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(360px,.8fr); height:calc(100vh - 60px) }}
iframe {{ width:100%; height:100%; border:0; background:#fff }}
aside {{ display:flex; min-width:0; min-height:0; flex-direction:column; border-left:1px solid var(--line); background:var(--panel) }}
.intro {{ padding:16px 20px 8px; color:var(--muted); font-size:13px }}
.chips {{ display:flex; gap:7px; overflow-x:auto; padding:11px 16px 8px; border-top:1px solid var(--line) }}
button {{ font:inherit; cursor:pointer }}
.chip {{ flex:none; color:#d8d1ff; background:#211d32; border:1px solid #3a3154; border-radius:999px; padding:6px 11px; font-size:12px }}
.chip:hover {{ background:#302649 }}
#messages {{ flex:1; min-height:0; overflow:auto; padding:18px 16px 24px; scroll-behavior:smooth }}
.welcome {{ max-width:440px; margin:24px auto; padding:22px; border:1px solid var(--line); border-radius:18px; background:#151925 }}
.welcome h2 {{ margin:0 0 6px; font-size:19px }} .welcome p {{ margin:0 0 16px; color:var(--muted); font-size:13px }}
.suggestions {{ display:grid; gap:8px }}
.suggestion {{ text-align:left; color:#dbe5f6; border:1px solid #30394b; background:#10141e; border-radius:10px; padding:9px 11px }}
.suggestion:hover {{ border-color:#8270c8 }}
.message {{ display:flex; align-items:flex-start; gap:9px; max-width:820px; margin:0 auto 18px }}
.message.user {{ justify-content:flex-end }}
.avatar {{ flex:none; display:grid; place-items:center; width:30px; height:30px; border-radius:50%; color:#eee8ff; background:#342858; font-size:14px }}
.bubble {{ max-width:min(88%,640px); padding:12px 15px; border-radius:16px; overflow-wrap:anywhere }}
.user .bubble {{ background:var(--user); border:1px solid #51438a; border-top-right-radius:5px }}
.assistant .bubble {{ background:#191e2a; border:1px solid #2d3545; border-top-left-radius:5px }}
.answer {{ line-height:1.7 }} .answer > :first-child {{ margin-top:0 }} .answer > :last-child {{ margin-bottom:0 }}
.answer h1,.answer h2,.answer h3 {{ margin:15px 0 7px; color:#f4f1ff; line-height:1.35 }}
.answer h1 {{ font-size:19px }} .answer h2 {{ font-size:17px }} .answer h3 {{ font-size:15px }}
.answer p {{ margin:7px 0 }} .answer ul,.answer ol {{ margin:7px 0; padding-left:23px }} .answer li {{ margin:3px 0 }}
.answer strong {{ color:#fff; font-weight:750 }} .answer code {{ padding:2px 5px; border-radius:5px; background:#0c1018; color:#c4b5fd; font-family:Consolas,monospace }}
.answer pre {{ overflow:auto; padding:11px; border-radius:8px; background:#0b0f16 }}
.answer pre code {{ padding:0; background:none; color:#e2e8f0 }}
.answer table {{ width:100%; border-collapse:collapse; margin:9px 0; font-size:13px }}
.answer th,.answer td {{ text-align:left; vertical-align:top; border:1px solid #3a4354; padding:6px 8px }}
.answer th {{ background:#242a38 }} .answer blockquote {{ margin:8px 0; padding-left:12px; border-left:3px solid var(--accent); color:#c4cad8 }}
.citation {{ display:inline-block; margin:0 2px; padding:0 5px; border-radius:5px; background:#253249; color:#b9dcff; font-size:11px; white-space:nowrap }}
.actions {{ display:flex; gap:5px; margin-top:9px }}
.action {{ border:1px solid transparent; background:transparent; color:#aab3c6; border-radius:7px; padding:3px 7px; font-size:12px }}
.action:hover,.action[aria-pressed="true"] {{ color:#ede9fe; background:#29253a; border-color:#484064 }}
.loading {{ display:flex; gap:5px; padding:5px 2px }}
.loading i {{ width:7px; height:7px; border-radius:50%; background:#b8a5ff; animation:pulse 1s infinite alternate }}
.loading i:nth-child(2) {{ animation-delay:.2s }} .loading i:nth-child(3) {{ animation-delay:.4s }}
@keyframes pulse {{ to {{ opacity:.25; transform:translateY(-3px) }} }}
.error {{ color:#fca5a5; padding:0 18px; min-height:4px }}
form {{ padding:9px 14px 14px; border-top:1px solid var(--line); background:#0e1119 }}
.composer {{ display:flex; align-items:flex-end; gap:9px; max-width:820px; margin:auto; padding:8px; border:1px solid #394254; border-radius:14px; background:#171b26 }}
textarea {{ flex:1; resize:none; min-height:42px; max-height:140px; border:0; outline:0; padding:9px; background:transparent; color:var(--text); font:inherit; line-height:1.5 }}
.send {{ flex:none; display:grid; place-items:center; width:40px; height:40px; border:0; border-radius:11px; color:white; background:#7357d5; font-size:22px }}
.send:hover {{ background:#8569e8 }} .send:disabled {{ opacity:.55; cursor:wait }}
.hint {{ max-width:820px; margin:6px auto 0; color:#8993a7; font-size:11px }}
@media(max-width:800px) {{ main {{ grid-template-columns:1fr; grid-template-rows:42vh minmax(420px,1fr); height:auto; min-height:calc(100vh - 60px) }} aside {{ border-left:0; border-top:1px solid var(--line); min-height:520px }} }}
</style>
</head>
<body>
<header><a href="/">← Dashboard</a><span class="title">{html.escape(subject)}</span><span class="grow"></span><a id="openFile" target="_blank" rel="noopener">Open file ↗</a></header>
<main>
<iframe id="pdf" title="Lecture notes PDF"></iframe>
<aside>
  <div class="intro">Your lecture study partner · answers grounded in these notes, with citations when available.</div>
  <div id="messages" aria-live="polite">
    <div id="welcome" class="welcome">
      <h2>Let’s study this lecture 📚</h2>
      <p>Ask a question or pick a starting point:</p>
      <div class="suggestions">
        <button class="suggestion" data-prompt="What are the main topics in this lecture?">What topics did we cover?</button>
        <button class="suggestion" data-prompt="Explain the most important concept simply, with an example.">Explain the most important concept</button>
        <button class="suggestion" data-prompt="What should I remember for the exam?">What should I remember?</button>
        <button class="suggestion" data-prompt="Create a 5-question quiz with answers from this lecture.">Quiz me on this lecture</button>
      </div>
    </div>
  </div>
  <div id="error" class="error" role="alert"></div>
  <nav class="chips" aria-label="Quick prompts">
    <button class="chip" data-prompt="Summarize the main ideas from this lecture.">Summarize</button>
    <button class="chip" data-prompt="List the topics covered in this lecture as bullets.">List topics</button>
    <button class="chip" data-prompt="Make me a short quiz from this lecture.">Quiz me</button>
    <button class="chip" data-prompt="Explain the main concept simply, with a concrete example.">Explain simply</button>
    <button class="chip" data-prompt="List the key terms and define each one.">Key terms</button>
  </nav>
  <form id="form">
    <div class="composer"><textarea id="question" maxlength="1000" rows="1" placeholder="Ask about this lecture…" aria-label="Your question" required></textarea><button id="send" class="send" type="submit" aria-label="Send message" title="Send">↑</button></div>
    <div class="hint">Enter to send · Shift+Enter for a new line</div>
  </form>
</aside>
</main>
<script>
const folder = {folder_json};
const documentName = {document_json};
const fileUrl = "/notes/" + folder.split("/").map(encodeURIComponent).join("/") + "/" + encodeURIComponent(documentName);
document.getElementById("pdf").src = fileUrl;
document.getElementById("openFile").href = fileUrl;
const messages = document.getElementById("messages");
const form = document.getElementById("form");
const input = document.getElementById("question");
const send = document.getElementById("send");
const error = document.getElementById("error");
const welcome = document.getElementById("welcome");
const history = [];
function escapeHtml(text) {{
  return text.replace(/[&<>"']/g, character => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})[character]);
}}
function inlineMarkdown(text) {{
  let value = escapeHtml(text);
  value = value.replace(/`([^`]+)`/g, "<code>$1</code>");
  value = value.replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
  value = value.replace(/\\*([^*]+)\\*/g, "<em>$1</em>");
  value = value.replace(/\\[([^\\]]+)\\]\\((https:\\/\\/[^ )]+)\\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return value.replace(/\\[(\\d{{2}}:\\d{{2}}(?::\\d{{2}})?)\\]/g, '<span class="citation">[$1]</span>');
}}
function renderMarkdown(markdown) {{
  const lines = markdown.replace(/\\r/g, "").split("\\n");
  const output = [];
  let index = 0;
  while (index < lines.length) {{
    const line = lines[index];
    if (!line.trim()) {{ index++; continue; }}
    if (line.startsWith("```")) {{
      const block = [];
      index++;
      while (index < lines.length && !lines[index].startsWith("```")) block.push(lines[index++]);
      if (index < lines.length) index++;
      output.push("<pre><code>" + escapeHtml(block.join("\\n")) + "</code></pre>");
      continue;
    }}
    if (/^\\s*\\|?.+\\|.+\\|?\\s*$/.test(line) && index + 1 < lines.length &&
        /^\\s*\\|?\\s*:?-{{3,}}:?\\s*(\\|\\s*:?-{{3,}}:?\\s*)+\\|?\\s*$/.test(lines[index + 1])) {{
      const cells = row => row.trim().replace(/^\\||\\|$/g, "").split("|").map(cell => cell.trim());
      const headers = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) rows.push(cells(lines[index++]));
      output.push("<table><thead><tr>" + headers.map(cell => "<th>" + inlineMarkdown(cell) + "</th>").join("") +
        "</tr></thead><tbody>" + rows.map(row => "<tr>" + headers.map((_, cell) =>
          "<td>" + inlineMarkdown(row[cell] || "") + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
      continue;
    }}
    const heading = line.match(/^(#{{1,3}})\\s+(.+)$/);
    if (heading) {{ const level = heading[1].length; output.push("<h" + level + ">" + inlineMarkdown(heading[2]) + "</h" + level + ">"); index++; continue; }}
    if (/^\\s*[-*+]\\s+/.test(line)) {{
      const items = [];
      while (index < lines.length && /^\\s*[-*+]\\s+/.test(lines[index])) items.push("<li>" + inlineMarkdown(lines[index++].replace(/^\\s*[-*+]\\s+/, "")) + "</li>");
      output.push("<ul>" + items.join("") + "</ul>");
      continue;
    }}
    if (/^\\s*\\d+[.)]\\s+/.test(line)) {{
      const items = [];
      while (index < lines.length && /^\\s*\\d+[.)]\\s+/.test(lines[index])) items.push("<li>" + inlineMarkdown(lines[index++].replace(/^\\s*\\d+[.)]\\s+/, "")) + "</li>");
      output.push("<ol>" + items.join("") + "</ol>");
      continue;
    }}
    if (/^>\\s?/.test(line)) {{ output.push("<blockquote>" + inlineMarkdown(line.replace(/^>\\s?/, "")) + "</blockquote>"); index++; continue; }}
    const paragraph = [line.trim()];
    index++;
    while (index < lines.length && lines[index].trim() &&
      !/^(#{1,3})\\s|^```|^\\s*[-*+]\\s+|^\\s*\\d+[.)]\\s+|^>\\s?/.test(lines[index])) paragraph.push(lines[index++].trim());
    output.push("<p>" + inlineMarkdown(paragraph.join(" ")) + "</p>");
  }}
  return output.join("");
}}
function scrollToLatest() {{ messages.scrollTop = messages.scrollHeight; }}
function addMessage(role, content) {{
  if (welcome) welcome.remove();
  const row = document.createElement("div");
  row.className = "message " + role;
  if (role === "assistant") {{
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "✦";
    avatar.setAttribute("aria-label", "Study assistant");
    row.appendChild(avatar);
  }}
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {{
    const answer = document.createElement("div");
    answer.className = "answer";
    answer.innerHTML = renderMarkdown(content);
    bubble.appendChild(answer);
    const actions = document.createElement("div");
    actions.className = "actions";
    const copy = document.createElement("button");
    copy.className = "action";
    copy.type = "button";
    copy.textContent = "Copy";
    copy.setAttribute("aria-label", "Copy answer");
    copy.addEventListener("click", async () => {{
      try {{ await navigator.clipboard.writeText(content); copy.textContent = "Copied"; }}
      catch {{ copy.textContent = "Select text to copy"; }}
    }});
    actions.appendChild(copy);
    for (const [label, icon] of [["Helpful", "👍"], ["Not helpful", "👎"]]) {{
      const reaction = document.createElement("button");
      reaction.className = "action";
      reaction.type = "button";
      reaction.textContent = icon;
      reaction.title = label;
      reaction.setAttribute("aria-label", label);
      reaction.setAttribute("aria-pressed", "false");
      reaction.addEventListener("click", () => {{
        for (const button of actions.querySelectorAll('[aria-label="Helpful"], [aria-label="Not helpful"]')) button.setAttribute("aria-pressed", "false");
        reaction.setAttribute("aria-pressed", "true");
      }});
      actions.appendChild(reaction);
    }}
    bubble.appendChild(actions);
  }} else {{
    bubble.textContent = content;
  }}
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToLatest();
}}
function addLoading() {{
  const row = document.createElement("div");
  row.className = "message assistant";
  row.id = "typing";
  row.innerHTML = '<div class="avatar" aria-label="Study assistant">✦</div><div class="bubble"><div class="loading" role="status" aria-label="Assistant is thinking"><i></i><i></i><i></i></div></div>';
  messages.appendChild(row);
  scrollToLatest();
}}
function autoGrow() {{ input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }}
async function ask(question) {{
  question = question.trim();
  if (!question || send.disabled) return;
  input.value = "";
  autoGrow();
  error.textContent = "";
  addMessage("user", question);
  send.disabled = true;
  addLoading();
  try {{
    const response = await fetch("/api/notes/" + folder.split("/").map(encodeURIComponent).join("/") + "/chat", {{
      method:"POST", headers:{{"Content-Type":"application/json"}},
      body:JSON.stringify({{question, history:history.slice(-6)}})
    }});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not get an answer.");
    document.getElementById("typing")?.remove();
    addMessage("assistant", data.answer);
    history.push({{role:"user", content:question}}, {{role:"assistant", content:data.answer}});
  }} catch (e) {{
    document.getElementById("typing")?.remove();
    error.textContent = e.message || "Could not reach the study assistant.";
  }} finally {{
    send.disabled = false;
    input.focus();
  }}
}}
form.addEventListener("submit", event => {{ event.preventDefault(); ask(input.value); }});
input.addEventListener("input", autoGrow);
input.addEventListener("keydown", event => {{
  if (event.key === "Enter" && !event.shiftKey) {{ event.preventDefault(); form.requestSubmit(); }}
}});
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {{
  ask(button.dataset.prompt);
}}));
</script>
</body>
</html>"""
