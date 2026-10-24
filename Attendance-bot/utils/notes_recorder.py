"""
Notes recorder — turns the live caption stream into notes/<Subject>/<date_time>/:

    transcript.md     full transcript (+ AI summary at the top when available)
    slides/           screenshots (when slide capture is on)
    notes.pdf         the lecture-notes document (cover, slides + notes, self-test, transcript)
    notes.html        same thing as a web page (fallback if no PDF could be rendered)
    meta.json         used by the dashboard's Notes tab
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from core import config_store
from core.logger import setup_logger
from utils import ai_notes, pdf_builder, lecture_insights

logger = setup_logger("Notes")
PKT = ZoneInfo("Asia/Karachi")
NOTES_ROOT = Path("notes")


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name or "").strip(" .") or "class"


@dataclass
class Segment:
    speaker: str
    text: str
    ts: datetime
    slide: int = 0
    alerted: bool = False


def merge_text(old: str, new: str) -> Optional[str]:
    """If `new` continues / revises `old` (same utterance) return the merged text, else None."""
    if not old or new == old:
        return new
    if new.startswith(old):
        return new
    if old.startswith(new) or (len(new) >= 10 and new in old):
        return old
    # Meet scrolls its caption window: the tail of old is the head of new
    for k in range(min(len(old), len(new)), 7, -1):
        if old[-k:] == new[:k]:
            return old + new[k:]
    # speech-to-text rewrote words in the middle
    if SequenceMatcher(None, old[:80], new[:80]).ratio() >= 0.7:
        return new if len(new) >= len(old) * 0.8 else old
    return None


def _caption_points(text: str) -> Tuple[str, List[str]]:
    """Make a conservative, caption-only explanation when AI notes are unavailable."""
    sentences = [part.strip(" -\t") for part in re.split(r"(?<=[.!?؟])\s+", text) if part.strip(" -\t")]
    if not sentences and text.strip():
        sentences = [text.strip()]
    if len(sentences) == 1 and len(sentences[0]) > 240:
        words = sentences[0].split()
        sentences = []
        current = ""
        for word in words:
            if current and len(current) + len(word) + 1 > 220:
                sentences.append(current)
                current = ""
            current = f"{current} {word}".strip()
        if current:
            sentences.append(current)
    first = sentences[0][:240] if sentences else ""
    bullets = sentences[1:5]
    return first, bullets


class NotesRecorder:
    def __init__(self, cls: Dict, config: Dict):
        self.cls = cls
        self.config = config
        self.subject = cls.get("subject", "Class")
        self.features = config_store.get_features(config)
        self.enabled = bool(self.features["notes"])
        self.started = datetime.now(PKT)
        self.dir = NOTES_ROOT / _safe(self.subject) / self.started.strftime("%Y-%m-%d_%H-%M")
        self.slides_dir = self.dir / "slides"
        self.segments: List[Segment] = []
        self._open: Dict[str, Segment] = {}
        self.slides: List[Dict] = []
        self.current_slide = 0
        self._last_flush = 0.0
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._write_meta(done=False)
            logger.info(f"[{self.subject}] Notes → {self.dir}")

    # ── live feed ───────────────────────────────────────────
    def feed(self, blocks: List[Tuple[str, str]]) -> List[Segment]:
        """blocks = [(speaker, text), ...] from the caption area. Returns segments that changed."""
        touched: List[Segment] = []
        now = datetime.now(PKT)
        for speaker, text in blocks:
            text = " ".join((text or "").split())
            if not text:
                continue
            seg = self._open.get(speaker)
            if seg:
                merged = merge_text(seg.text, text)
                if merged is not None:
                    if merged != seg.text:
                        seg.text = merged
                        touched.append(seg)
                    continue
            seg = Segment(speaker, text, now, self.current_slide)
            self.segments.append(seg)
            self._open[speaker] = seg
            touched.append(seg)
        if self.enabled:
            self._maybe_flush()
        return touched

    def add_audio_transcript(self, text: str) -> bool:
        """Store local audio ASR unless the same recent speech is already captioned."""
        normalized = lambda value: re.sub(r"\W+", " ", value.casefold()).strip()
        whisper_text = normalized(text)
        if not whisper_text:
            return False
        now = datetime.now(PKT)
        recent = [
            segment.text for segment in self.segments
            if (now - segment.ts).total_seconds() <= 30
        ]
        whisper_words = whisper_text.split()
        caption_words = normalized(" ".join(recent)).split()
        if len(whisper_words) >= 6 and caption_words:
            matcher = SequenceMatcher(None, whisper_words, caption_words, autojunk=False)
            matched_words = sum(block.size for block in matcher.get_matching_blocks())
            if matched_words / len(whisper_words) >= 0.7:
                return False
        elif len(whisper_text) >= 25 and whisper_text in " ".join(caption_words):
            return False
        self.feed([("Local audio (Whisper)", text)])
        return True

    def add_slide(self, rel_file: str, kind: str = "slide") -> int:
        n = len(self.slides) + 1
        now = datetime.now(PKT)
        self.slides.append({"n": n, "file": rel_file, "time": now.strftime("%H:%M:%S"),
                            "t": now.timestamp(), "kind": kind})
        self.current_slide = n
        return n

    # ── files ───────────────────────────────────────────────
    def _maybe_flush(self):
        if time.time() - self._last_flush >= 30:
            self.flush()

    def flush(self):
        """Write the transcript so far (so a crash / Ctrl+C never loses it)."""
        if not self.enabled:
            return
        self._last_flush = time.time()
        try:
            (self.dir / "transcript.md").write_text(self._render_md(None), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write transcript: {e}")

    def _transcript_md(self, segments: Optional[List[Segment]] = None) -> str:
        out, last = [], None
        for s in segments if segments is not None else self.segments:
            if self.slides and s.slide != last:
                out.append(f"\n### Slide {s.slide}\n" if s.slide else "\n### Before the first slide\n")
                last = s.slide
            who = f"**{s.speaker}:** " if s.speaker else ""
            out.append(f"- `{s.ts:%H:%M:%S}` {who}{s.text}")
        return "\n".join(out)

    def _plain(self, segments: Optional[List[Segment]] = None) -> str:
        return "\n".join(
            f"[{s.ts:%H:%M}] {s.speaker + ': ' if s.speaker else ''}{s.text}"
            for s in (segments if segments is not None else self.segments)
        )

    def _render_md(self, summary: Optional[Dict], flags: Optional[List[Dict]] = None,
                   segments: Optional[List[Segment]] = None) -> str:
        parts = [f"# {self.subject} — {self.started:%Y-%m-%d}",
                 f"*Attendance Bot · started {self.started:%H:%M} · captions are auto-generated and may contain errors*\n"]
        if segments is not None:
            parts.append("*AI-corrected captions; compare with `transcript.md` for the original automatic captions.*\n")
        if summary:
            if summary.get("title"):
                parts.append(f"**{summary['title']}**\n")
            if summary.get("summary"):
                parts.append("## Overview\n" + "\n".join(f"- {x}" for x in summary["summary"]) + "\n")
            for section in summary.get("sections", []):
                parts.append(f"## {section['heading']}\n")
                if section.get("key_idea"):
                    parts.append(f"**Key idea:** {section['key_idea']}\n")
                for key, head in (("bullets", "Concepts"), ("equations", "Equations & formulas"),
                                  ("examples", "Examples")):
                    if section.get(key):
                        parts.append(f"### {head}\n" + "\n".join(f"- {x}" for x in section[key]) + "\n")
            for key, head in (("emphasis", "Exam radar (stressed by the teacher)"),
                              ("homework", "Homework / tasks"), ("key_terms", "Key terms")):
                if summary.get(key):
                    parts.append(f"## {head}\n" + "\n".join(f"- {x}" for x in summary[key]) + "\n")
            if summary.get("deadlines"):
                parts.append("## Deadlines\n" + "\n".join(
                    f"- {d.get('item', '')} — {d.get('date', '')}" if isinstance(d, dict) else f"- {d}"
                    for d in summary["deadlines"]) + "\n")
            quiz = [q for q in (summary.get("quiz") or []) if isinstance(q, dict) and q.get("q")]
            if quiz:
                parts.append("## Self-test\n" + "\n".join(
                    f"{i}. {q['q']}\n   - *{q.get('a', '')}*" for i, q in enumerate(quiz, 1)) + "\n")
        if flags:
            parts.append("## Flagged moments\n" + "\n".join(
                f"- **{f['label']}** `{f['time']}`: {f['text']}" for f in flags) + "\n")
        parts.append("## Corrected transcript\n" if segments is not None else "## Transcript\n")
        parts.append(self._transcript_md(segments) or "*(no captions were captured)*")
        return "\n".join(parts) + "\n"

    def _write_meta(self, done: bool, pdf: bool = False, html: bool = False,
                    summary: bool = False, corrected_transcript: bool = False):
        meta = {
            "subject": self.subject, "date": self.started.strftime("%Y-%m-%d"),
            "time": self.started.strftime("%H:%M"), "folder": self.dir.relative_to(NOTES_ROOT).as_posix(),
            "segments": len(self.segments), "slides": len(self.slides),
            "done": done, "pdf": pdf, "html": html, "summary": summary,
            "corrected_transcript": corrected_transcript,
        }
        try:
            (self.dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── end of class ────────────────────────────────────────
    def _transcript_groups(self, segments: Optional[List[Segment]] = None):
        """[(heading, [(time, speaker, text), ...]), ...] for the PDF appendix."""
        groups, cur_key, cur = [], None, None
        slide_time = {sl["n"]: sl["time"][:5] for sl in self.slides}
        for sg in segments if segments is not None else self.segments:
            if self.slides:
                key = sg.slide
                head = (f"Slide {sg.slide} — {slide_time.get(sg.slide, '')}" if sg.slide else "Before the first slide")
            else:
                key = (sg.ts.hour * 60 + sg.ts.minute) // 5
                head = f"{sg.ts:%H:%M}"
            if key != cur_key:
                cur_key, cur = key, []
                groups.append((head, cur))
            cur.append((sg.ts.strftime("%H:%M:%S"), sg.speaker, sg.text))
        return groups

    async def finalize(self) -> Optional[Path]:
        if not self.enabled:
            return None
        if not self.segments and not self.slides:
            try:
                for f in self.dir.glob("*"):
                    f.unlink()
                self.dir.rmdir()
            except Exception:
                pass
            logger.warning(
                f"[{self.subject}] No Meet captions or slides captured — check that captions "
                "are enabled, the language matches, and shared video audio is included; no notes saved."
            )
            return None

        ended = datetime.now(PKT)
        have_key = bool(ai_notes.api_key(self.config))
        use_ai = bool(self.features["ai_summary"]) and have_key
        if self.features["ai_summary"] and not have_key:
            logger.info(f"[{self.subject}] AI summary skipped — no API key (Dashboard → Settings). "
                        "Building notes with offline analysis instead.")

        transcript_segments = self.segments
        corrected_transcript_saved = False
        if use_ai and self.segments:
            logger.info(f"[{self.subject}] Proofreading caption segments with AI...")
            raw_segments = [
                {"time": f"{sg.ts:%H:%M:%S}", "speaker": sg.speaker, "text": sg.text}
                for sg in self.segments
            ]
            corrected = await ai_notes.correct_transcript(self.config, raw_segments)
            if corrected is None:
                logger.warning(f"[{self.subject}] Keeping original captions; AI correction was unavailable.")
            else:
                transcript_segments = [
                    Segment(sg.speaker, fixed["text"], sg.ts, sg.slide, sg.alerted)
                    for sg, fixed in zip(self.segments, corrected)
                ]
                try:
                    (self.dir / "transcript_corrected.md").write_text(
                        self._render_md(None, segments=transcript_segments), encoding="utf-8")
                    corrected_transcript_saved = True
                    logger.info(f"[{self.subject}] AI-corrected transcript saved.")
                except Exception as e:
                    logger.error(f"[{self.subject}] Could not write corrected transcript: {e}")

        plain = self._plain(transcript_segments)
        summary = None
        if use_ai and len(plain.strip()) >= 15:
            logger.info(f"[{self.subject}] Generating structured AI study notes...")
            summary = await ai_notes.summarize(self.config, plain)
            if summary is None:
                logger.error(
                    f"[{self.subject}] AI note generation failed; the PDF will contain the "
                    "transcript and offline analysis only. Check the provider error above."
                )

        per: Dict[int, str] = {}
        for sg in self.segments:
            if sg.slide:
                per[sg.slide] = (per.get(sg.slide, "") + " " + sg.text).strip()
        ai_slides: Dict[int, Dict] = {}
        if self.slides and use_ai:
            logger.info(f"[{self.subject}] Writing notes for {len(self.slides)} slides...")
            ai_slides = await ai_notes.slide_notes(self.config, per)

        flags = lecture_insights.find_flags(self.segments)
        rows = []
        for i, sl in enumerate(self.slides):
            t_next = self.slides[i + 1]["t"] if i + 1 < len(self.slides) else ended.timestamp()
            ai = ai_slides.get(sl["n"], {})
            raw = " ".join(per.get(sl["n"], "").split())[:900]
            caption_takeaway, caption_bullets = _caption_points(raw)
            ai_takeaway = str(ai.get("takeaway") or "").strip()
            ai_bullets = ai.get("bullets") or []
            rows.append({
                "n": sl["n"], "file": sl["file"], "time": sl["time"], "kind": sl.get("kind", "slide"),
                "dur_s": max(1.0, t_next - sl["t"]),
                "takeaway": ai_takeaway or caption_takeaway,
                "bullets": ai_bullets or caption_bullets,
                "summary_source": "AI summary" if ai_takeaway or ai_bullets else "Caption notes",
                "raw": raw,
                "flags": [f for f in flags if f["slide"] == sl["n"]],
            })
        ctx = {
            "subject": self.subject, "date_str": self.started.strftime("%A, %d %B %Y · %H:%M"),
            "end_time": ended.strftime("%H:%M:%S"),
            "duration_s": (ended - self.started).total_seconds(),
            "words": sum(len(sg.text.split()) for sg in self.segments),
            "speakers": len({sg.speaker for sg in self.segments if sg.speaker}),
            "slides": rows, "summary": summary, "flags": flags,
            "ai_requested": use_ai,
            "keywords": lecture_insights.top_keywords(plain),
            "transcript": self._transcript_groups(transcript_segments),
            "transcript_is_ai_corrected": transcript_segments is not self.segments,
        }
        pdf_options = {
            "include_transcript": self.features.get("pdf_include_transcript", False),
        }
        html_ok = pdf_ok = False
        try:
            html_path = self.dir / "notes.html"
            html_path.write_text(pdf_builder.build_html(ctx, pdf_options), encoding="utf-8")
            html_ok = True
            pdf_ok = await pdf_builder.render_pdf(
                html_path, self.dir / "notes.pdf",
                f"{self.subject} · {self.started:%Y-%m-%d}",
                self.features.get("pdf_paper_size", "A4"))
        except Exception as e:
            logger.error(f"[{self.subject}] Could not build the notes document: {e}")

        try:
            (self.dir / "transcript.md").write_text(self._render_md(summary, flags), encoding="utf-8")
        except Exception as e:
            logger.error(f"Could not write transcript: {e}")
        self._write_meta(done=True, pdf=pdf_ok, html=html_ok, summary=bool(summary),
                         corrected_transcript=corrected_transcript_saved)
        logger.info(f"[{self.subject}] Notes saved → {self.dir}" + (" (notes.pdf ready)" if pdf_ok else ""))
        return self.dir
