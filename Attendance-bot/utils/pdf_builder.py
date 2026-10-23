"""
Lecture-notes document builder (HTML → PDF).

Pages:
  1  Cover      – subject, stats, slide timeline bar, AI summary, exam radar,
                  homework checklist, key terms
  2  At a glance – contact sheet of every slide (click a thumbnail to jump)
  3… Slides     – one page per slide: screenshot, takeaway, notes, flagged moments
  …  Self-test  – questions, then an answers page (AI)
  …  Transcript – the full timed transcript

Works with no slides (talk-only lecture) and with no AI key (offline flags,
keywords and raw captions are used instead).

The HTML uses relative image paths (slides/slide_001.jpg) so notes.html works
standalone. The PDF is rendered by a separate headless Chromium (page.pdf() only
works headless; the meeting browser is headed). If no Chromium can be launched
the HTML is kept — open it and use Print → Save as PDF.
"""

import html
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
section.page { break-after: page; }
section.page:last-of-type { break-after: auto; }
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
.card h2 { font-size: 10pt; text-transform: uppercase; letter-spacing: .1em; color: #475569; margin-bottom: 7px; }
.card.summary { border-left: 5px solid #6366f1; }
.card.radar { border-left: 5px solid #e11d48; background: #fff7f8; }
.card.todo { border-left: 5px solid #2563eb; }
.card.terms { border-left: 5px solid #10b981; }
.card.lecture { border-left: 5px solid #7c3aed; }
.card.lecture h3 { font-size: 13pt; color: #312e81; margin-bottom: 6px; }
.key-idea { color: #334155; margin-bottom: 7px; }
.formula { background: #f1f5f9; border-left: 3px solid #7c3aed; padding: 6px 10px;
  margin: 5px 0; font-family: Consolas, "Cambria Math", monospace; white-space: pre-wrap; }
.example { border-left: 3px solid #10b981; padding: 5px 10px; margin: 5px 0; background: #f0fdf4; }
ol.num { margin: 0; padding: 0; list-style: none; counter-reset: n; }
ol.num li { counter-increment: n; position: relative; padding-left: 28px; margin-bottom: 6px; }
ol.num li::before { content: counter(n); position: absolute; left: 0; top: 1px; width: 19px; height: 19px;
  border-radius: 50%; background: #6366f1; color: #fff; font-size: 8.5pt; font-weight: 700; text-align: center; line-height: 19px; }
ul.check { list-style: none; margin: 0; padding: 0; }
ul.check li { position: relative; padding-left: 24px; margin-bottom: 5px; }
ul.check li::before { content: ""; position: absolute; left: 0; top: 4px; width: 12px; height: 12px;
  border: 2px solid #2563eb; border-radius: 3px; }
ul.plain { margin: 0; padding-left: 18px; } ul.plain li { margin-bottom: 4px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; border-radius: 6px; padding: 2px 9px; font-size: 9.5pt; font-weight: 600; }
.pill { display: inline-block; border-radius: 5px; padding: 1px 8px; font-size: 7.5pt; font-weight: 800;
  letter-spacing: .06em; color: #fff; vertical-align: 1px; }
.flag { display: flex; gap: 9px; align-items: flex-start; margin-bottom: 7px; }
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
.tr h3 { font-size: 9.5pt; margin: 12px 0 4px; color: #4338ca; border-bottom: 1px solid #e2e8f0; padding-bottom: 2px; }
.tr p { font-size: 8.8pt; margin-bottom: 3px; color: #1e293b; break-inside: avoid; }
.tr .tm { color: #94a3b8; font-family: Consolas, monospace; font-size: 8pt; margin-right: 6px; }
.tr .sp { color: #6366f1; font-weight: 700; margin-right: 4px; }
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _ul(items: List[str], cls: str = "plain") -> str:
    return f'<ul class="{cls}">' + "".join(f'<li dir="auto">{_e(i)}</li>' for i in items) + "</ul>"


def _pill(kind: str, label: str) -> str:
    return f'<span class="pill" style="background:{FLAG_COLORS.get(kind, "#64748b")}">{_e(label)}</span>'


def _color(n: int) -> str:
    return PALETTE[(n - 1) % len(PALETTE)]


def build_html(ctx: Dict, options: Optional[Dict] = None) -> str:
    options = options or {}
    subject, slides = ctx["subject"], ctx.get("slides", [])
    summary = ctx.get("summary") or {}
    flags = ctx.get("flags", [])
    total_s = max(1, ctx.get("duration_s", 1))

    chips = [fmt_dur(ctx.get("duration_s", 0))]
    if slides:
        chips.append(f"{len(slides)} slides")
    chips += [f'{ctx.get("words", 0):,} words', f'{ctx.get("speakers", 0)} speaker(s)']
    if flags:
        chips.append(f"{len(flags)} flagged moments")

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
        if summary.get("title"):
            cover.append(f'<div class="card summary"><h2>{_e("Lecture in one line")}</h2>'
                         f'<div dir="auto" style="font-weight:700;font-size:12pt">{_e(summary["title"])}</div></div>')
        if summary.get("summary"):
            cover.append('<div class="card summary"><h2>Summary</h2><ol class="num">'
                         + "".join(f'<li dir="auto">{_e(x)}</li>' for x in summary["summary"]) + "</ol></div>")

    radar = ""
    if summary.get("emphasis"):
        radar += _ul([str(x) for x in summary["emphasis"]])
    if flags:
        radar += "".join(
            f'<div class="flag">{_pill(f["kind"], f["label"])}<div dir="auto">{_e(f["text"])} '
            f'<span class="t">· {_e(f["time"])}{" · slide " + str(f["slide"]) if f["slide"] else ""}</span></div></div>'
            for f in flags)
    if radar:
        cover.append(f'<div class="card radar"><h2>Exam radar — what the teacher stressed</h2>{radar}</div>')

    todo = []
    for h in summary.get("homework", []) or []:
        todo.append(str(h))
    for d in summary.get("deadlines", []) or []:
        todo.append(f'{d.get("item", "")} — due {d.get("date", "")}' if isinstance(d, dict) else str(d))
    if todo:
        cover.append('<div class="card todo"><h2>Homework &amp; deadlines</h2>' + _ul(todo, "check") + "</div>")

    terms = [str(t) for t in (summary.get("key_terms") or [])] or ctx.get("keywords", [])
    if terms:
        lab = "Key terms" if summary.get("key_terms") else "Most repeated terms"
        cover.append(f'<div class="card terms"><h2>{lab}</h2><div class="tags">'
                     + "".join(f'<span class="tag" dir="auto">{_e(t)}</span>' for t in terms) + "</div></div>")

    if not summary:
        if ctx.get("ai_requested"):
            cover.append('<div class="hint">AI notes could not be generated for this class. '
                         'The transcript is preserved separately; check the bot log for the provider error.</div>')
        else:
            cover.append('<div class="hint">AI notes were not generated. Add an AI provider key and enable AI summaries '
                         'in Dashboard → Settings to create organized study notes.</div>')
    pages = [f'<section class="page">{"".join(cover)}</section>']

    # ── structured AI study notes ─────────────────────────
    if summary.get("sections"):
        cards = []
        for section in summary["sections"]:
            body = [f'<h3 dir="auto">{_e(section.get("heading", ""))}</h3>']
            if section.get("key_idea"):
                body.append(f'<p class="key-idea" dir="auto"><b>Key idea:</b> {_e(section["key_idea"])}</p>')
            if section.get("bullets"):
                body.append(_ul(section["bullets"]))
            if section.get("equations"):
                body.append('<h4>Equations &amp; formulas</h4>')
                body.extend(f'<div class="formula" dir="auto">{_e(item)}</div>' for item in section["equations"])
            if section.get("examples"):
                body.append('<h4>Examples</h4>')
                body.extend(f'<div class="example" dir="auto">{_e(item)}</div>' for item in section["examples"])
            cards.append(f'<div class="card lecture">{"".join(body)}</div>')
        pages.append('<section class="page"><h2 class="pg">Organized study notes</h2>'
                     '<div class="sub">Key concepts, explanations, formulas, and examples from the lecture.</div>'
                     + "".join(cards) + "</section>")

    # ── at a glance ─────────────────────────────────────
    if slides:
        thumbs = "".join(
            f'<a class="thumb" href="#s{s["n"]}"><img src="{_e(s["file"])}" alt=""><div class="cap">'
            f'<b>{"Snapshot" if s["kind"] == "moment" else "Slide"} {s["n"]}</b><span>{_e(s["time"])}</span></div></a>'
            for s in slides)
        pages.append(f'<section class="page"><h2 class="pg">Lecture at a glance</h2>'
                     f'<div class="sub">Every slide in order — click one to jump to its notes.</div><div class="grid">{thumbs}</div></section>')

    # ── slide pages ─────────────────────────────────────
    for s in slides:
        label = "Snapshot" if s["kind"] == "moment" else "Slide"
        parts = [f'<div class="sh"><div class="num" style="background:{_color(s["n"])}">{s["n"]}</div>'
                 f'<div><div class="st">{label} {s["n"]} <span class="sm">of {len(slides)}</span></div>'
                 f'<div class="sm">{_e(s["time"])} · on screen {_e(fmt_dur(s["dur_s"]))}</div></div>'
                 + ('<span class="snapbadge">live snapshot (video / whiteboard)</span>' if s["kind"] == "moment" else "")
                 + "</div>",
                 f'<img src="{_e(s["file"])}" alt="{label} {s["n"]}">']
        if s.get("takeaway"):
            parts.append(f'<div class="take"><small>Key takeaway</small><span dir="auto">{_e(s["takeaway"])}</span></div>')
        if s.get("bullets"):
            parts.append('<div class="notes"><h3>Notes</h3>' + _ul(s["bullets"]) + "</div>")
        elif s.get("raw"):
            parts.append(f'<div class="notes"><h3>What was said (raw captions)</h3><div class="raw" dir="auto">{_e(s["raw"])}</div></div>')
        else:
            parts.append('<div class="notes none">No captions were spoken while this was on screen.</div>')
        for f in s.get("flags", []):
            parts.append(f'<div class="flag" style="margin-top:8px">{_pill(f["kind"], f["label"])}'
                         f'<div dir="auto">{_e(f["text"])} <span class="t">· {_e(f["time"])}</span></div></div>')
        pages.append(f'<section class="page slide" id="s{s["n"]}">{"".join(parts)}</section>')

    # ── self-test ───────────────────────────────────────
    quiz = [q for q in (summary.get("quiz") or []) if isinstance(q, dict) and q.get("q")]
    if quiz:
        qs = "".join(f'<div class="qa"><div class="q" dir="auto">{i}. {_e(q["q"])}</div></div>' for i, q in enumerate(quiz, 1))
        ans = "".join(f'<div class="qa"><div class="q" dir="auto">{i}. {_e(q["q"])}</div>'
                      f'<div class="a" dir="auto">{_e(q.get("a", ""))}</div></div>' for i, q in enumerate(quiz, 1))
        pages.append(f'<section class="page"><h2 class="pg">Self-test</h2><div class="sub">Try to answer before you turn the page.</div>{qs}</section>')
        pages.append(f'<section class="page"><h2 class="pg">Answers</h2><div class="sub">&nbsp;</div>{ans}</section>')

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

    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{_e(subject)} — {_e(ctx["date_str"])}</title>'
            f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")


async def render_pdf(html_path: Path, pdf_path: Path, footer_text: str = "", paper_size: str = "A4") -> bool:
    footer = (f'<div style="width:100%;font-size:8px;color:#94a3b8;padding:0 14mm;display:flex;'
              f'justify-content:space-between;font-family:Arial,sans-serif"><span>{_e(footer_text)}</span>'
              f'<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
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
