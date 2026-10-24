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
* {{ box-sizing:border-box }} body {{ margin:0; background:#0a0a0f; color:#e2e8f0; font:15px/1.5 'Segoe UI',system-ui,sans-serif }}
header {{ height:58px; display:flex; align-items:center; gap:14px; padding:0 18px; border-bottom:1px solid #252538 }}
a {{ color:#7dd3fc; text-decoration:none }} a:hover {{ text-decoration:underline }}
.title {{ font-weight:750; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }} .grow {{ flex:1 }}
main {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(320px,.8fr); height:calc(100vh - 58px) }}
iframe {{ width:100%; height:100%; border:0; background:#fff }}
aside {{ display:flex; min-height:0; flex-direction:column; border-left:1px solid #252538 }}
.intro {{ padding:16px 18px 10px; color:#94a3b8; font-size:13px }}
#messages {{ flex:1; min-height:0; overflow:auto; padding:8px 16px }}
.msg {{ white-space:pre-wrap; overflow-wrap:anywhere; padding:10px 12px; border-radius:12px; margin:8px 0; max-width:95% }}
.user {{ background:#34226b; margin-left:auto }} .assistant {{ background:#181824; border:1px solid #252538 }}
.error {{ color:#fca5a5; padding:0 18px 8px; min-height:20px }}
form {{ display:flex; gap:8px; padding:12px 14px 16px; border-top:1px solid #252538 }}
textarea {{ flex:1; resize:none; min-height:46px; max-height:120px; border:1px solid #34344a; border-radius:9px; padding:10px; background:#12121a; color:#e2e8f0; font:inherit }}
button {{ border:0; border-radius:9px; padding:0 16px; color:white; background:#7c3aed; font-weight:700; cursor:pointer }}
button:disabled {{ opacity:.55; cursor:wait }}
@media(max-width:800px) {{ main {{ grid-template-columns:1fr; grid-template-rows:48vh minmax(320px,1fr); height:auto; min-height:calc(100vh - 58px) }} aside {{ border-left:0; border-top:1px solid #252538; min-height:420px }} }}
</style>
</head>
<body>
<header><a href="/">← Dashboard</a><span class="title">{html.escape(subject)}</span><span class="grow"></span><a id="openFile" target="_blank" rel="noopener">Open file ↗</a></header>
<main>
<iframe id="pdf" title="Lecture notes PDF"></iframe>
<aside>
  <div class="intro">Ask questions about this class. Answers are based on its saved notes and transcript; citations are included when available.</div>
  <div id="messages" aria-live="polite"><div class="msg assistant">Hi! Ask me to explain a topic, formula, example, or point from these notes.</div></div>
  <div id="error" class="error" role="alert"></div>
  <form id="form"><textarea id="question" maxlength="1000" placeholder="Ask about this lecture…" aria-label="Your question" required></textarea><button id="send" type="submit">Ask</button></form>
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
const history = [];
function addMessage(role, content) {{
  const node = document.createElement("div");
  node.className = "msg " + role;
  node.textContent = content;
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
}}
form.addEventListener("submit", async event => {{
  event.preventDefault();
  const question = input.value.trim();
  if (!question || send.disabled) return;
  input.value = "";
  error.textContent = "";
  addMessage("user", question);
  send.disabled = true;
  send.textContent = "Thinking…";
  try {{
    const response = await fetch("/api/notes/" + folder.split("/").map(encodeURIComponent).join("/") + "/chat", {{
      method:"POST", headers:{{"Content-Type":"application/json"}},
      body:JSON.stringify({{question, history:history.slice(-6)}})
    }});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not get an answer.");
    addMessage("assistant", data.answer);
    history.push({{role:"user", content:question}}, {{role:"assistant", content:data.answer}});
  }} catch (e) {{
    error.textContent = e.message || "Could not reach the study assistant.";
  }} finally {{
    send.disabled = false;
    send.textContent = "Ask";
    input.focus();
  }}
}});
input.addEventListener("keydown", event => {{
  if (event.key === "Enter" && !event.shiftKey) {{ event.preventDefault(); form.requestSubmit(); }}
}});
</script>
</body>
</html>"""
