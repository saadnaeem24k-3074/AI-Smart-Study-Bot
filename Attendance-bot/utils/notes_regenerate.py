"""Rebuild notes.pdf from a saved lecture folder ("Regenerate notes" in the dashboard).

It runs the SAME pipeline as the end-of-class job, so the regenerated notes contain everything the
first version did: the slide / snapshot pages with their screenshots and per-slide notes, the
questions asked (and the bot's replies), flagged moments, and - for conversations between peers -
the speaker-attributed meeting minutes.

What it reads from the lecture folder:
    transcript.md          timed, speaker-labelled captions (with "### Slide N" markers)
    slides.json            slide timings (written by new recordings)
    slides/slide_NNN.jpg   the screenshots; folders recorded before slides.json existed are
                           rebuilt from these files and the slide markers in transcript.md
    class_questions.json   questions heard in class (falls back to the "Questions asked" section)
"""
import json
import re
import types
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from core import config_store
from core.logger import setup_logger
from utils import ai_notes, lecture_insights, pdf_builder
from utils.notes_recorder import (
    PKT, NotesRecorder, Segment, build_slide_rows, detect_session_mode, prepare_class_questions,
    resolve_notes_scope, speaker_stats,
)

logger = setup_logger("NotesRegenerate")

_TRANSCRIPT_HEAD = re.compile(r"^## Transcript\s*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"^## ", re.MULTILINE)
_SLIDE_HEAD = re.compile(r"^### (?:Slide (\d+)|Before the first slide)\s*$")
_LINE = re.compile(r"^- `(\d{2}:\d{2}:\d{2})` (?:\*\*(.+?):\*\* )?(.*)$")
_QUESTIONS_HEAD = re.compile(r"^## Questions asked in (?:class|the meeting)\s*$", re.MULTILINE)
_QUESTION = re.compile(r"^- `(\d{2}:\d{2}:\d{2})` (.*?)(\s*\*\*\(asked to you\)\*\*)?\s*$")
_BOT_REPLY = re.compile(r"^\s+- Bot's chat reply: (.*)$")
_SLIDE_FILE = re.compile(r"slide_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


def _lecture_date(meta: Dict) -> datetime:
    try:
        return datetime.strptime(str(meta.get("date", "")), "%Y-%m-%d").replace(tzinfo=PKT)
    except ValueError:
        return datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)


def _at(day: datetime, clock: str) -> datetime:
    hour, minute, second = (int(x) for x in clock.split(":"))
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def parse_transcript(raw: str, meta: Dict) -> List[Segment]:
    """transcript.md -> Segment objects (time, speaker, text and the slide each line was spoken during)."""
    start = _TRANSCRIPT_HEAD.search(raw)
    if not start:
        return []
    body = raw[start.end():]
    following = _NEXT_SECTION.search(body)
    if following:
        body = body[:following.start()]
    day = _lecture_date(meta)
    segments: List[Segment] = []
    slide, previous = 0, None
    for line in body.splitlines():
        heading = _SLIDE_HEAD.match(line.strip())
        if heading:
            slide = int(heading.group(1)) if heading.group(1) else 0
            continue
        found = _LINE.match(line.strip())
        if not found:
            continue
        clock, speaker, text = found.groups()
        when = _at(day, clock)
        if previous and when < previous - timedelta(hours=12):      # the lecture ran past midnight
            day += timedelta(days=1)
            when += timedelta(days=1)
        previous = when
        segments.append(Segment(speaker or "", text.strip(), when, slide))
    return segments


def load_slides(directory: Path, segments: List[Segment]) -> List[Dict]:
    """The lecture's slides / snapshots: slides.json when present, otherwise rebuilt from the screenshots."""
    saved = directory / "slides.json"
    if saved.is_file():
        try:
            slides = json.loads(saved.read_text(encoding="utf-8"))
            slides = [s for s in slides if isinstance(s, dict) and s.get("file") and (directory / s["file"]).is_file()]
            if slides:
                return sorted(slides, key=lambda s: s["n"])
        except (OSError, ValueError, KeyError):
            logger.warning("slides.json could not be read; rebuilding the slide list from the screenshots.")
    first_caption: Dict[int, datetime] = {}
    for seg in segments:
        if seg.slide and seg.slide not in first_caption:
            first_caption[seg.slide] = seg.ts
    slides = []
    for path in sorted((directory / "slides").glob("slide_*")):
        number = _SLIDE_FILE.search(path.name)
        if not number:
            continue
        n = int(number.group(1))
        when = first_caption.get(n) or datetime.fromtimestamp(path.stat().st_mtime, PKT)
        slides.append({"n": n, "file": f"slides/{path.name}", "time": when.strftime("%H:%M:%S"),
                       "t": when.timestamp(), "kind": "slide"})
    return sorted(slides, key=lambda s: s["n"])


def assign_slides_by_time(segments: List[Segment], slides: List[Dict]) -> None:
    """Folders without '### Slide N' markers: a caption belongs to the latest slide shown before it."""
    for seg in segments:
        seg.slide = max((s["n"] for s in slides if s["t"] <= seg.ts.timestamp()), default=0)


def load_questions(directory: Path, raw: str) -> List[Dict]:
    saved = directory / "class_questions.json"
    if saved.is_file():
        try:
            items = json.loads(saved.read_text(encoding="utf-8"))
            if isinstance(items, list):
                return [q for q in items if isinstance(q, dict) and q.get("text")]
        except (OSError, ValueError):
            pass
    head = _QUESTIONS_HEAD.search(raw)
    if not head:
        return []
    body = raw[head.end():]
    following = _NEXT_SECTION.search(body)
    questions: List[Dict] = []
    for line in (body[:following.start()] if following else body).splitlines():
        reply = _BOT_REPLY.match(line)
        if reply and questions:
            questions[-1]["bot_answer"] = reply.group(1).strip()
            continue
        found = _QUESTION.match(line.strip())
        if found:
            clock, text, to_me = found.groups()
            questions.append({"time": clock, "text": text.strip(), "to_me": bool(to_me), "bot_answer": ""})
    return questions


async def regenerate(directory: Path, config: dict, instructions: str = "") -> bool:
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    raw = (directory / "transcript.md").read_text(encoding="utf-8") if (directory / "transcript.md").is_file() else ""
    segments = parse_transcript(raw, meta)
    if sum(len(s.text.split()) for s in segments) < 30:
        logger.error("Not enough transcript text to write notes.")
        return False

    features = config_store.get_features(config)
    subject = meta.get("subject", "Lecture")
    slides = load_slides(directory, segments)
    if slides and not any(seg.slide for seg in segments):
        assign_slides_by_time(segments, slides)
    mode = detect_session_mode(subject, segments, features.get("session_mode", "auto"))
    participants = speaker_stats(segments)
    shim = types.SimpleNamespace(slides=slides, segments=segments)       # the recorder's formatting helpers
    scope = resolve_notes_scope(features.get("notes_scope", "auto"), mode)
    discussed = scope == "discussed"
    plain = (NotesRecorder._plain_meeting(shim, segments) if discussed
             else NotesRecorder._plain(shim, segments))

    if discussed:
        summary = await ai_notes.summarize_meeting(config, plain, participants, instructions)
    else:
        summary = await ai_notes.summarize(config, plain, instructions)
    if not summary:
        return False

    per: Dict[int, str] = {}
    for seg in segments:
        if seg.slide:
            per[seg.slide] = (per.get(seg.slide, "") + " " + seg.text).strip()
    ai_slides = await ai_notes.slide_notes(config, per, "discussed" if discussed else mode) if slides else {}
    flags = lecture_insights.find_flags(segments)
    ends = max([segments[-1].ts.timestamp() + 20] + [s["t"] + 20 for s in slides])
    rows = build_slide_rows(slides, per, ai_slides, flags, ends)
    class_questions = await prepare_class_questions(config, load_questions(directory, raw), plain, True,
                                                   generate_answers=not discussed)

    keywords = lecture_insights.top_keywords(plain)
    title = pdf_builder.lecture_title({"subject": subject, "summary": summary, "keywords": keywords})
    started, finished = segments[0].ts, segments[-1].ts
    ctx = {
        "subject": subject, "title": title, "date_str": started.strftime("%d %B %Y"),
        "start_time": meta.get("time") or started.strftime("%H:%M"), "end_time": finished.strftime("%H:%M:%S"),
        "duration_s": meta.get("duration_s") or (finished - started).total_seconds(),
        "words": sum(len(s.text.split()) for s in segments),
        "speakers": len({s.speaker for s in segments if s.speaker}),
        "slides": rows, "summary": summary, "flags": flags, "class_questions": class_questions,
        "ai_requested": True, "keywords": keywords, "mode": mode, "notes_scope": scope,
        "participants": participants,
        "speaker_digest": lecture_insights.speaker_digest(segments) if mode == "meeting" else [],
        "speaker_labels_missing": mode == "meeting" and not participants,
        "transcript": NotesRecorder._transcript_groups(shim, segments),
        "transcript_is_ai_corrected": False,
    }
    html_path = directory / "notes.html"
    html_path.write_text(
        pdf_builder.build_html(ctx, {"include_transcript": features.get("pdf_include_transcript", False)}),
        encoding="utf-8")
    pdf_ok = await pdf_builder.render_pdf(
        html_path, directory / "notes.pdf", features.get("pdf_paper_size", "A4"), title)
    meta.update(done=True, pdf=bool(pdf_ok), html=True, summary=True, lecture_title=title, slides=len(slides))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Regenerated notes for '{subject}' with {len(slides)} slides and {len(class_questions)} questions.")
    return bool(pdf_ok)
