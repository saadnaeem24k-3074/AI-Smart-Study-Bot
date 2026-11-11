"""
Lecture-notes document builder (HTML → PDF).

Pages:
  1  Cover      – lecture title, stats, slide timeline, summary and key moments
  2  At a glance – contact sheet of every slide (click a thumbnail to jump)
  2… Study notes – slide explanations, defined glossary terms, examples and steps
  …  Self-test  – questions and answers together
  …  Transcript – the full timed transcript

Works with no slides (talk-only lecture) and with no AI key (offline complete-sentence
flags and caption notes are used instead).

The HTML uses relative image paths (slides/slide_001.jpg) so notes.html works
standalone. The PDF is rendered by a separate headless Chromium (page.pdf() only
works headless; the meeting browser is headed). If no Chromium can be launched
the HTML is kept — open it and use Print → Save as PDF.
"""

import html
import re
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright

from core.logger import setup_logger
from utils.lecture_insights import fmt_dur

logger = setup_logger("PDFBuilder")

PALETTE = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316"]
FLAG_COLORS = {"EXAM": "#e11d48", "IMPORTANT": "#d97706", "DEADLINE": "#2563eb"}

CSS = """
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: #0f172a; font-size: 10.5pt; line-height: 1.55;
  font-family: "Segoe UI", "Noto Sans", "Noto Naskh Arabic", "Urdu Typesetting", Arial, sans-serif; }
[dir="auto"], .rtl { unicode-bidi: plaintext; }
h1, h2, h3, p { margin: 0; }
section.page { break-after: page; break-inside: auto; }
section.page:last-of-type { break-after: auto; }
.page > h2, .card h2, .slide .sh { break-after: avoid; }
.pg { font-size: 18pt !important; margin-bottom: 5px !important; }
.notes-start { margin-top: 14px; }
.hero { border-radius: 14px; padding: 22px 24px; color: #fff;
  background: linear-gradient(135deg, #4338ca 0%, #7c3aed 55%, #db2777 120%); }
.kicker { font-size: 8.5pt; letter-spacing: .18em; opacity: .85; font-weight: 700; }
.hero h1 { font-size: 27pt; line-height: 1.15; margin: 4px 0 2px; }
.when { opacity: .9; font-size: 10pt; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.chip { background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.3); border-radius: 999px;
  padding: 3px 11px; font-size: 9pt; font-weight: 600; }
.card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px 15px; margin-top: 12px;
  break-inside: avoid; background: #fff; }
.card h2 { font-size: 11pt; text-transform: uppercase; letter-spacing: .1em; color: #475569; margin-bottom: 7px; }
.card.summary { border-left: 5px solid #6366f1; }
.card.radar { border-left: 5px solid #e11d48; background: #fff7f8; }
.card.takeaways { border-left: 5px solid #0891b2; background: #f0f9ff; }
.card.todo { border-left: 5px solid #2563eb; }
.card.terms { border-left: 5px solid #10b981; }
.card.terms h3 { color: #047857; font-size: 12pt; margin-bottom: 7px; }
.card.lecture { border-left: 5px solid #7c3aed; padding: 14px 17px; margin-top: 14px; }
.card.lecture h3 { font-size: 15pt; line-height: 1.25; color: #312e81; margin-bottom: 8px; }
.card.lecture h4 { color: #475569; font-size: 10pt; margin: 9px 0 5px; break-after: avoid; }
.section-icon { display: inline-block; margin-right: 6px; font-size: 12pt; }
.key-idea { color: #312e81; margin: 0 0 9px; padding: 8px 11px; border-left: 3px solid #6366f1;
  border-radius: 0 7px 7px 0; background: #eef2ff; break-inside: avoid; }
.formula { background: #f1f5f9; border-left: 3px solid #7c3aed; padding: 6px 10px;
  margin: 5px 0; font-family: Consolas, "Cambria Math", monospace; white-space: pre-wrap; }
.examples { margin-top: 9px; padding: 9px 12px; border: 1px solid #fde68a; border-left: 4px solid #f59e0b;
  border-radius: 8px; background: #fffbeb; break-inside: avoid; }
.examples h4 { margin: 0 0 5px !important; color: #92400e !important; }
.example { color: #78350f; margin: 4px 0; }
.glossary { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
.glossary th, .glossary td { text-align: left; vertical-align: top; padding: 7px 9px; border-bottom: 1px solid #e2e8f0; }
.glossary th { color: #047857; background: #ecfdf5; font-weight: 750; }
.glossary tbody tr:nth-child(even) { background: #f8fafc; }
.glossary td:first-child { width: 30%; color: #047857; font-weight: 750; }
.diagram { margin: 11px 0; padding: 12px 14px; border: 1px solid #c7d2fe; border-radius: 11px;
  background: linear-gradient(135deg, #f8faff, #f0fdfa); break-inside: avoid;
  box-shadow: 0 2px 8px rgba(49, 46, 129, .07); }
.diagram-title { margin-bottom: 10px; color: #4338ca; font-size: 8pt; font-weight: 800;
  letter-spacing: .08em; text-transform: uppercase; }
.flow { display: flex; align-items: stretch; justify-content: center; gap: 7px; flex-wrap: wrap; }
.flow-node { flex: 1 1 105px; display: flex; align-items: center; justify-content: center; min-height: 42px;
  padding: 7px 9px; border: 1px solid #c7d2fe; border-radius: 8px; background: #fff;
  color: #3730a3; text-align: center; font-weight: 700; box-shadow: 0 1px 3px rgba(49, 46, 129, .08); }
.flow-arrow { align-self: center; color: #7c3aed; font-size: 13pt; font-weight: 900; }
.tree-root { width: fit-content; margin: 0 auto 11px; padding: 7px 14px; border-radius: 8px;
  background: #312e81; color: white; text-align: center; font-weight: 750; }
.tree-branches { display: flex; justify-content: center; gap: 8px; padding-top: 9px;
  border-top: 2px solid #a5b4fc; }
.tree-branch { flex: 1; padding: 8px 10px; border-top: 3px solid #06b6d4; border-radius: 7px;
  background: #ecfeff; text-align: center; font-weight: 700; }
.tree-branch ul { margin: 4px 0 0; padding-left: 16px; color: #334155; text-align: left; font-weight: 400; }
.compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.compare-group { padding: 9px 11px; border: 1px solid #c7d2fe; border-radius: 8px;
  background: #eef2ff; break-inside: avoid; }
.compare-group:nth-child(2) { background: #ecfeff; }
.compare-group:nth-child(3) { background: #f0fdf4; }
.compare-group b { color: #3730a3; }
.compare-group ul { margin: 4px 0 0; padding-left: 16px; }
.quickref { margin-top: 14px; padding: 12px 14px; border: 1px solid #c7d2fe; border-radius: 12px;
  background: linear-gradient(135deg, #eef2ff, #f0fdfa); break-inside: avoid; }
.quickref h2 { margin-bottom: 7px; color: #312e81; font-size: 13pt; }
.quickref-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 7px; }
.quickref-item { padding: 6px 8px; border-radius: 6px; background: rgba(255,255,255,.8); }
.quickref-item b { color: #4338ca; }
ol.num { margin: 0; padding: 0; list-style: none; counter-reset: n; }
ol.num li { counter-increment: n; position: relative; padding-left: 28px; margin-bottom: 6px; }
ol.num li::before { content: counter(n); position: absolute; left: 0; top: 1px; width: 19px; height: 19px;
  border-radius: 50%; background: #6366f1; color: #fff; font-size: 8.5pt; font-weight: 700; text-align: center; line-height: 19px; }
ul.check { list-style: none; margin: 0; padding: 0; }
ul.check li { position: relative; padding-left: 24px; margin-bottom: 5px; }
ul.check li::before { content: ""; position: absolute; left: 0; top: 4px; width: 12px; height: 12px;
  border: 2px solid #2563eb; border-radius: 3px; }
ul.plain { margin: 0; padding-left: 18px; } ul.plain li { margin-bottom: 4px; }
.pill { display: inline-block; border-radius: 5px; padding: 1px 8px; font-size: 7.5pt; font-weight: 800;
  letter-spacing: .06em; color: #fff; vertical-align: 1px; }
.flag { display: flex; gap: 9px; align-items: flex-start; margin-bottom: 7px; break-inside: avoid; }
.flag .pill { flex: none; margin-top: 3px; } .flag .t { color: #64748b; font-size: 8.5pt; }
.hint { margin-top: 12px; padding: 9px 13px; border-radius: 10px; background: #f1f5f9; color: #475569; font-size: 9pt; }
.tl { display: flex; height: 26px; border-radius: 8px; overflow: hidden; margin-top: 14px; border: 1px solid #e2e8f0; }
.tl div { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 8pt; font-weight: 700; min-width: 6px; overflow: hidden; }
.tl .snap { background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.25) 0 4px, transparent 4px 8px); }
.tlcap { display: flex; justify-content: space-between; color: #64748b; font-size: 8pt; margin-top: 3px; }
h2.pg { font-size: 15pt; margin-bottom: 3px; } .sub { color: #64748b; font-size: 9pt; margin-bottom: 12px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.thumb { display: block; text-decoration: none; color: inherit; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; break-inside: avoid; }
.thumb img { display: block; width: 100%; aspect-ratio: 16/9; object-fit: cover; background: #f1f5f9; }
.thumb .cap { display: flex; justify-content: space-between; align-items: center; padding: 5px 9px; font-size: 8.5pt; }
.thumb .cap b { color: #4338ca; } .thumb .cap span { color: #64748b; }
.slide .sh { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.slide .num { width: 38px; height: 38px; border-radius: 11px; color: #fff; font-weight: 800; font-size: 15pt;
  text-align: center; line-height: 38px; flex: none; }
.slide .st { font-weight: 700; font-size: 12pt; } .slide .sm { color: #64748b; font-size: 9pt; }
.slide .snapbadge { margin-left: auto; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 6px; padding: 2px 9px; font-size: 8pt; font-weight: 700; }
.slide img { display: block; width: 100%; max-height: 118mm; object-fit: contain; border-radius: 10px;
  border: 1px solid #cbd5e1; box-shadow: 0 6px 18px rgba(15,23,42,.14); background: #0f172a; }
.take { margin-top: 12px; padding: 10px 14px; border-radius: 10px; background: #eef2ff; border-left: 5px solid #6366f1; font-weight: 600; }
.take small { display: block; color: #6366f1; text-transform: uppercase; letter-spacing: .12em; font-size: 7.5pt; margin-bottom: 2px; }
.notes { margin-top: 10px; }
.notes h3 { font-size: 9pt; text-transform: uppercase; letter-spacing: .1em; color: #475569; margin-bottom: 4px; }
.raw { background: #f8fafc; border-left: 3px solid #cbd5e1; padding: 7px 10px; border-radius: 0 8px 8px 0; color: #334155; font-size: 9.5pt; white-space: pre-wrap; }
.none { color: #94a3b8; font-style: italic; font-size: 9pt; }
.qa { margin-bottom: 11px; break-inside: avoid; } .qa .q { font-weight: 700; } .qa .a { color: #047857; margin-top: 2px; }
.selftest { margin-top: 14px; break-inside: avoid; }
.quiz-card { break-inside: avoid; }
.tr h3 { font-size: 9.5pt; margin: 12px 0 4px; color: #4338ca; border-bottom: 1px solid #e2e8f0; padding-bottom: 2px; }
.tr p { font-size: 8.8pt; margin-bottom: 3px; color: #1e293b; break-inside: avoid; }
.tr .tm { color: #94a3b8; font-family: Consolas, monospace; font-size: 8pt; margin-right: 6px; }
.tr .sp { color: #6366f1; font-weight: 700; margin-right: 4px; }
.qa { padding: 8px 10px; border-radius: 8px; background: #f8fafc; }
.qa .a { margin-top: 5px; padding: 6px 9px; border-radius: 6px; background: #ecfdf5; }
.qa .q { break-after: avoid; }

body{font-family:"Times New Roman","Noto Serif",Georgia,serif;font-size:11pt;line-height:1.5;color:#000;counter-reset:sec}
.hero{background:none !important;color:#000;border-radius:0;padding:0 0 12px;border-bottom:3px double #000;text-align:center}
.kicker{opacity:1;letter-spacing:.3em}.when{opacity:1}.chips{justify-content:center}
.chip{background:none;border:1px solid #000;border-radius:0;color:#000}
.card{border:0 !important;border-radius:0;background:none !important;padding:0;margin-top:16px}
.card h2,h2.pg{font-size:14pt;color:#000;text-transform:none;letter-spacing:0;border-bottom:1.5px solid #000;padding-bottom:3px;margin-bottom:8px}
.card h2::before,h2.pg::before{counter-increment:sec;content:counter(sec) ". "}
.notes-start{counter-reset:sub}
.card.lecture{margin-top:18px;break-inside:auto !important}.card.lecture h3{color:#000;font-size:12.5pt;border-bottom:1px solid #000}
.card.lecture h3::before{counter-increment:sub;content:counter(sub) ". "}
.card.lecture h4,.notes h3{color:#000;letter-spacing:0}.section-icon{display:none}
.key-idea{background:#fff;border:1px solid #000;border-left:5px solid #000;border-radius:0;color:#000}
.formula{background:#fff;border:1px solid #000;border-radius:0}
.examples{background:#fff;border:1px dashed #000;border-radius:0}.examples h4,.example{color:#000 !important}
.glossary{border:1px solid #000}.glossary th{background:#000;color:#fff}
.glossary th,.glossary td{border:1px solid #000}.glossary td:first-child{color:#000}
.glossary tbody tr:nth-child(even){background:#f2f2f2}
ol.num li::before{background:#000;border-radius:0}ul.check li::before{border-color:#000;border-radius:0}
.pill{background:#000 !important;border-radius:0}.flag .t,.sub,.sm,.tm,.sp{color:#333}
.tl{filter:grayscale(1)}.thumb{border:1px solid #000;border-radius:0}.thumb .cap b{color:#000}
.slide .num{background:#000 !important;border-radius:0}.slide img{border:1px solid #000;border-radius:0;box-shadow:none}
.take{background:#f2f2f2;border-left:5px solid #000;border-radius:0}.take small{color:#000}
.raw{background:#f2f2f2;border-left:3px solid #000;border-radius:0}
.qa,.qa .a{background:none;border:1px solid #000;border-radius:0}.qa .a{border:0;border-top:1px dashed #000;border-radius:0}
.quickref{background:none;border:1px solid #000;border-radius:0}.quickref h2{color:#000}.quickref-item{background:none;border:1px solid #000;border-radius:0}.quickref-item b{color:#000}
.hint{background:#f2f2f2;border-radius:0;color:#000}.tr h3{color:#000;border-bottom:1px solid #000}
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _ul(items: List[str], cls: str = "plain") -> str:
    return f'<ul class="{cls}">' + "".join(f'<li dir="auto">{_e(i)}</li>' for i in items) + "</ul>"


def _pill(kind: str, label: str) -> str:
    return f'<span class="pill" style="background:{FLAG_COLORS.get(kind, "#64748b")}">{_e(label)}</span>'


def _color(n: int) -> str:
    return PALETTE[(n - 1) % len(PALETTE)]


def _section_icon(heading: str) -> str:
    text = heading.casefold()
    for words, icon in (
        (("test", "exam"), "🧪"),
        (("phase", "process", "step", "life cycle", "lifecycle"), "➡️"),
        (("type", "category", "class", "hierarch"), "🌿"),
        (("compare", "versus", " vs ", "difference"), "⚖️"),
        (("architecture", "design", "structure"), "🏗️"),
        (("formula", "equation", "calculate"), "∑"),
    ):
        if any(word in text for word in words):
            return icon
    return "✦"


def _diagram(diagram: Dict) -> str:
    title = f'<div class="diagram-title">{_e(diagram.get("title") or "Concept map")}</div>'
    diagram_type = diagram.get("type")
    if diagram_type in ("process", "analogy"):
        nodes = diagram.get("nodes") or []
        body = '<div class="flow">' + "".join(
            (f'<span class="flow-arrow" aria-hidden="true">→</span>' if index else "")
            + f'<span class="flow-node" dir="auto">{_e(node)}</span>'
            for index, node in enumerate(nodes)
        ) + "</div>"
    elif diagram_type == "hierarchy":
        branches = "".join(
            f'<div class="tree-branch" dir="auto">{_e(branch["label"])}'
            + (_ul(branch["children"]) if branch.get("children") else "")
            + "</div>"
            for branch in diagram.get("branches", [])
        )
        body = (f'<div class="tree-root" dir="auto">{_e(diagram.get("root", ""))}</div>'
                f'<div class="tree-branches">{branches}</div>')
    elif diagram_type == "comparison":
        groups = "".join(
            f'<div class="compare-group" dir="auto"><b>{_e(group["label"])}</b>'
            + (_ul(group["items"]) if group.get("items") else "")
            + "</div>"
            for group in diagram.get("groups", [])
        )
        body = f'<div class="compare">{groups}</div>'
    else:
        return ""
    return f'<div class="diagram">{title}{body}</div>'


def _timestamp(value: str, start_time: str) -> str:
    try:
        current = [int(part) for part in value.split(":")]
        start = [int(part) for part in start_time.split(":")]
        elapsed = (current[0] * 3600 + current[1] * 60 + current[2]
                   - start[0] * 3600 - start[1] * 60 - start[2]) % 86400
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
    except (TypeError, ValueError, IndexError):
        return value


def _unprefix_number(value: str) -> str:
    return re.sub(r"^\s*\d+[.)]\s*", "", str(value))


def lecture_title(ctx: Dict) -> str:
    summary = ctx.get("summary") or {}
    for candidate in (
        ctx.get("title"),
        summary.get("title"),
        next((section.get("heading") for section in (summary.get("sections") or [])
              if isinstance(section, dict) and section.get("heading")), ""),
        ctx.get("subject"),
    ):
        title = " ".join(str(candidate or "").split()).strip()
        if title and not re.fullmatch(
            r"(quick\s*join|meeting|google\s*meet|zoom|wisper|whisper|class)",
            title,
            flags=re.I,
        ):
            return title[:120]
    keywords = [str(word).strip() for word in (ctx.get("keywords") or []) if str(word).strip()]
    if keywords:
        return ", ".join(keywords[:3])
    return "Lecture Notes"


def _radar_items(emphasis: List[str], flags: List[Dict]) -> List[Dict]:
    items, seen = [], []
    for item in [*flags, *({"text": text, "kind": "", "label": "", "time": "", "slide": 0}
                          for text in emphasis)]:
        text = " ".join(str(item.get("text") or "").split())
        words = set(re.findall(r"\w+", text.casefold(), re.UNICODE))
        if not words or any(
            len(words & previous) / min(len(words), len(previous)) >= 0.8
            for previous in seen
        ):
            continue
        seen.append(words)
        items.append({**item, "text": text})
    return items


def build_html(ctx: Dict, options: Optional[Dict] = None) -> str:
    options = options or {}
    subject, slides = lecture_title(ctx), ctx.get("slides", [])
    summary = ctx.get("summary") or {}
    flags = ctx.get("flags", [])
    total_s = max(1, ctx.get("duration_s", 1))

    chips = [fmt_dur(ctx.get("duration_s", 0))]
    if slides:
        chips.append(f"{len(slides)} slides")
    chips += [f'{ctx.get("words", 0):,} words', f'{ctx.get("speakers", 0)} speaker(s)']
    if flags:
        chips.append(f"{len(flags)} flagged moment{'s' if len(flags) != 1 else ''}")

    cover = [f'<div class="hero"><div class="kicker">LECTURE NOTES</div><h1 dir="auto">{_e(subject)}</h1>'
             f'<div class="when">{_e(ctx["date_str"])}</div>'
             f'<div class="chips">{"".join(f"<span class=chip>{_e(c)}</span>" for c in chips)}</div></div>']

    if slides:       # timeline bar: how long each slide was on screen
        bar = "".join(
            f'<div class="{"snap" if s["kind"] == "moment" else ""}" title="Slide {s["n"]} · {_e(fmt_dur(s["dur_s"]))}" '
            f'style="flex:{max(s["dur_s"], total_s * 0.015):.1f};background-color:{_color(s["n"])}">{s["n"]}</div>'
            for s in slides)
        cover.append(f'<div class="tl">{bar}</div><div class="tlcap"><span>{_e(slides[0]["time"])}</span>'
                     f'<span>time on each slide</span><span>{_e(ctx.get("end_time", ""))}</span></div>')

    if summary:
        if summary.get("summary"):
            cover.append('<div class="card summary"><h2>Summary</h2><ol class="num">'
                         + "".join(f'<li dir="auto">{_e(x)}</li>' for x in summary["summary"]) + "</ol></div>")

    radar_items = _radar_items(summary.get("emphasis") or [], flags)
    if flags or any(not item.get("kind") for item in radar_items):
        quotes = []
        for item in flags:
            timestamp = _timestamp(str(item.get("time") or ""), str(ctx.get("start_time") or ""))
            slide = item.get("slide")
            location = " · ".join(
                value for value in (timestamp, f"Slide {slide}" if slide else "") if value
            )
            quotes.append(
                f'<div class="flag">{_pill(str(item.get("kind") or ""), item.get("label") or "Flagged")}'
                f'<div dir="auto"><q>{_e(item.get("text", ""))}</q>'
                f'{f" <span class=t>· {_e(location)}</span>" if location else ""}</div></div>'
            )
        takeaways = [
            f'<li dir="auto">{_e(item["text"])}</li>'
            for item in radar_items if not item.get("kind")
        ]
        cover.append(
            f'<div class="card radar"><h2>Key moments</h2>{"".join(quotes) or "<div class=none>No flagged quotes.</div>"}</div>'
        )
        if takeaways:
            cover.append(
                '<div class="card takeaways"><h2>Key takeaways</h2><ul class="plain">'
                + "".join(takeaways) + "</ul></div>"
            )

    todo = []
    for h in summary.get("homework", []) or []:
        todo.append(str(h))
    for d in summary.get("deadlines", []) or []:
        todo.append(f'{d.get("item", "")} — due {d.get("date", "")}' if isinstance(d, dict) else str(d))
    if todo:
        cover.append('<div class="card todo"><h2>Homework &amp; deadlines</h2>' + _ul(todo, "check") + "</div>")

    terms = [
        term for term in (summary.get("key_terms") or [])
        if isinstance(term, dict) and term.get("term") and term.get("definition")
    ]

    if not summary:
        if ctx.get("ai_requested"):
            cover.append('<div class="hint">AI notes could not be generated for this class. '
                         'The transcript is preserved separately; check the bot log for the provider error.</div>')
        else:
            cover.append('<div class="hint">AI notes were not generated. Add an AI provider key and enable AI summaries '
                         'in Dashboard → Settings to create organized study notes.</div>')
    # ── structured AI study notes ─────────────────────────
    if summary.get("sections"):
        cards = []
        for section in summary["sections"]:
            heading = str(section.get("heading", ""))
            body = [f'<h3 dir="auto"><span class="section-icon">{_section_icon(heading)}</span>{_e(heading)}</h3>']
            if section.get("key_idea"):
                body.append(f'<p class="key-idea" dir="auto"><b>Key idea:</b> {_e(section["key_idea"])}</p>')
            for diagram in section.get("diagrams") or []:
                body.append(_diagram(diagram))
            if section.get("bullets"):
                body.append(_ul(section["bullets"]))
            if section.get("steps"):
                body.append('<h4>Process</h4><ol class="num">'
                            + "".join(f'<li dir="auto">{_e(_unprefix_number(item))}</li>'
                                      for item in section["steps"])
                            + "</ol>")
            if section.get("equations"):
                body.append('<h4>Equations &amp; formulas</h4>')
                body.extend(f'<div class="formula" dir="auto">{_e(item)}</div>' for item in section["equations"])
            if section.get("examples"):
                body.append(
                    '<div class="examples"><h4>💡 Examples</h4>'
                    + "".join(f'<div class="example" dir="auto">{_e(item)}</div>' for item in section["examples"])
                    + "</div>"
                )
            cards.append(f'<div class="card lecture">{"".join(body)}</div>')
        if terms:
            cards.append(
                '<div class="card terms"><h3>Key terms</h3><table class="glossary"><thead><tr><th>Term</th><th>Definition</th></tr></thead><tbody>'
                + "".join(
                    f'<tr><td dir="auto">{_e(term["term"])}</td><td dir="auto">{_e(term["definition"])}</td></tr>'
                    for term in terms
                )
                + "</tbody></table></div>"
            )
        cover.append(
            '<div class="notes-start"><h2 class="pg">Organized study notes</h2>'
            '<div class="sub">Key concepts, explanations, formulas, and examples from the lecture.</div>'
            + "".join(cards) + "</div>"
        )
    elif terms:
        cover.append(
            '<div class="notes-start"><h2 class="pg">Key terms</h2>'
            '<div class="card terms"><table class="glossary"><thead><tr><th>Term</th><th>Definition</th></tr></thead><tbody>'
            + "".join(
                f'<tr><td dir="auto">{_e(term["term"])}</td><td dir="auto">{_e(term["definition"])}</td></tr>'
                for term in terms
            )
            + "</tbody></table></div></div>"
        )
    pages = [f'<section class="page cover">{"".join(cover)}</section>']

    # ── at a glance ─────────────────────────────────────
    if slides:
        thumbs = "".join(
            f'<a class="thumb" href="#s{s["n"]}"><img src="{_e(s["file"])}" alt=""><div class="cap">'
            f'<b>{"Snapshot" if s["kind"] == "moment" else "Slide"} {s["n"]}</b><span>{_e(s["time"])}</span></div></a>'
            for s in slides)
        glance = (
            '<h2 class="pg">Lecture at a glance</h2>'
            '<div class="sub">Every slide in order — click one to jump to its notes.</div>'
            f'<div class="grid">{thumbs}</div>'
        )
        if not summary.get("sections") and not terms:
            cover.append(f'<div class="notes-start">{glance}</div>')
            pages[0] = f'<section class="page cover">{"".join(cover)}</section>'
        else:
            pages.append(f'<section class="page">{glance}</section>')

    # ── slide pages ─────────────────────────────────────
    for s in slides:
        label = "Snapshot" if s["kind"] == "moment" else "Slide"
        parts = [f'<div class="sh"><div class="num" style="background:{_color(s["n"])}">{s["n"]}</div>'
                 f'<div><div class="st">{label} {s["n"]} <span class="sm">of {len(slides)}</span></div>'
                 f'<div class="sm">{_e(s["time"])} · on screen {_e(fmt_dur(s["dur_s"]))}</div></div>'
                 + ('<span class="snapbadge">live snapshot (video / whiteboard)</span>' if s["kind"] == "moment" else "")
                 + "</div>",
                 f'<img src="{_e(s["file"])}" alt="{label} {s["n"]}">']
        parts.append(f'<div class="take"><small>What this screenshot relates to · {_e(s.get("summary_source") or "Lecture notes")}</small>'
                     + (f'<span dir="auto">{_e(s["takeaway"])}</span>' if s.get("takeaway")
                        else '<span>No related captions were captured during this moment.</span>') + '</div>')
        if s.get("bullets"):
            parts.append('<div class="notes"><h3>What the teacher explained</h3>' + _ul(s["bullets"]) + "</div>")
        elif s.get("raw"):
            parts.append(f'<div class="notes"><h3>What the teacher explained (captions)</h3><div class="raw" dir="auto">{_e(s["raw"])}</div></div>')
        else:
            parts.append('<div class="notes none">No related explanation was captured while this was on screen.</div>')
        pages.append(f'<section class="page slide" id="s{s["n"]}">{"".join(parts)}</section>')

    # ── self-test ───────────────────────────────────────
    quiz = [q for q in (summary.get("quiz") or []) if isinstance(q, dict) and q.get("q")]
    if quiz:
        qs = "".join(
            f'<div class="qa"><div class="q" dir="auto">{i}. {_e(q["q"])}</div>'
            f'<div class="a" dir="auto"><b>Check your answer:</b> {_e(q.get("a", ""))}</div></div>'
            for i, q in enumerate(quiz, 1)
        )
        pages.append(
            f'<section class="page selftest"><h2 class="pg">Self-test &amp; answers</h2>'
            f'<div class="sub">Review each question, then check the answer.</div>'
            f'<div class="card quiz-card">{qs}</div></section>'
        )

    # ── questions asked in class ────────────────────────
    cqs = [q for q in (ctx.get("class_questions") or []) if q.get("text")]
    if cqs:
        items = "".join(
            f'<div class="qa"><div class="q" dir="auto">{i}. {_e(q["text"])} '
            f'<span class="sm">{_e(q.get("time", ""))}</span>'
            + (' <span class="snapbadge">Asked to you</span>' if q.get("to_me") else "")
            + '</div>'
            + (f'<div class="a" dir="auto"><b>{"Bot reply in chat" if q.get("bot_answer") else "Answer"}:</b> '
               f'{_e(q.get("answer", ""))}</div>' if q.get("answer") else "")
            + '</div>'
            for i, q in enumerate(cqs, 1)
        )
        pages.append(
            f'<section class="page selftest"><h2 class="pg">Questions Asked in Class</h2>'
            f'<div class="sub">Every question raised during the lecture, with its answer.</div>'
            f'<div class="card quiz-card">{items}</div></section>'
        )

    # ── transcript ──────────────────────────────────────
    if ctx.get("transcript") and options.get("include_transcript", False):
        groups = []
        for title, lines in ctx["transcript"]:
            body = "".join(
                f'<p dir="auto"><span class="tm">{_e(t)}</span>'
                + (f'<span class="sp">{_e(sp)}:</span>' if sp else "") + f'{_e(tx)}</p>'
                for t, sp, tx in lines)
            groups.append(f"<h3>{_e(title)}</h3>{body}")
        transcript_note = (
            "AI-corrected captions — compare uncertain wording against transcript.md."
            if ctx.get("transcript_is_ai_corrected")
            else "Auto-generated captions — expect recognition errors."
        )
        pages.append('<section class="page tr"><h2 class="pg">Full transcript</h2>'
                     f'<div class="sub">{_e(transcript_note)}</div>' + "".join(groups) + "</section>")

    quick_items = [
        f'<div class="quickref-item" dir="auto"><b>{_e(section.get("heading", "Topic"))}</b>'
        + (f'<br>{_e(section.get("key_idea", ""))}' if section.get("key_idea") else "")
        + "</div>"
        for section in (summary.get("sections") or [])[:6]
    ]
    if quick_items:
        pages.append(
            '<section class="page"><div class="quickref"><h2>Quick reference</h2>'
            '<div class="quickref-grid">' + "".join(quick_items) + "</div></div></section>"
        )

    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{_e(subject)} — {_e(ctx["date_str"])}</title>'
            f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")


async def render_pdf(
    html_path: Path,
    pdf_path: Path,
    paper_size: str = "A4",
    document_title: str = "Lecture Notes",
) -> bool:
    footer_title = html.escape(document_title, quote=True)
    footer = ('<div style="width:100%;font-size:8px;color:#64748b;text-align:center;'
              'font-family:Arial,sans-serif"><span>'
              f'{footer_title} · <span class="pageNumber"></span>/<span class="totalPages"></span>'
              '</span></div>')
    try:
        async with async_playwright() as p:
            browser = None
            for kwargs in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
                try:
                    browser = await p.chromium.launch(headless=True, **kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                logger.warning("No headless Chromium available — keeping notes.html (open it and Print → Save as PDF)")
                return False
            try:
                page = await browser.new_page()
                await page.goto(html_path.resolve().as_uri(), wait_until="load")
                await page.pdf(path=str(pdf_path), format=paper_size, print_background=True,
                               display_header_footer=True, header_template="<div></div>", footer_template=footer,
                               margin={"top": "12mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})
            finally:
                await browser.close()
        return pdf_path.exists()
    except Exception as e:
        logger.error(f"PDF render failed: {e}")
        return False
