"""Rebuild notes.pdf from a saved transcript.md - used when AI note generation failed at the end of class."""
import json
from pathlib import Path

from core import config_store
from core.logger import setup_logger
from utils import ai_notes, lecture_insights, pdf_builder

logger = setup_logger("NotesRegenerate")


async def regenerate(directory: Path, config: dict, instructions: str = "") -> bool:
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    raw = (directory / "transcript.md").read_text(encoding="utf-8") if (directory / "transcript.md").is_file() else ""
    body = raw.split("## Transcript", 1)[-1].strip()
    if len(body.split()) < 30:
        logger.error("Not enough transcript text to write notes.")
        return False
    summary = await ai_notes.summarize(config, body, instructions)
    if not summary:
        return False
    keywords = lecture_insights.top_keywords(body)
    subject = meta.get("subject", "Lecture")
    title = pdf_builder.lecture_title({"subject": subject, "summary": summary, "keywords": keywords})
    ctx = {
        "subject": subject, "title": title, "date_str": meta.get("date", ""),
        "start_time": meta.get("time", ""), "end_time": "", "duration_s": meta.get("duration_s", 0) or 0,
        "words": len(body.split()), "speakers": meta.get("speakers", 0) or 0, "slides": [],
        "summary": summary, "flags": [], "ai_requested": True, "keywords": keywords,
        "transcript": [], "transcript_is_ai_corrected": False,
    }
    html_path = directory / "notes.html"
    html_path.write_text(pdf_builder.build_html(ctx, {"include_transcript": False}), encoding="utf-8")
    paper = config_store.get_features(config).get("pdf_paper_size", "A4")
    pdf_ok = await pdf_builder.render_pdf(html_path, directory / "notes.pdf", paper, title)
    meta.update(done=True, pdf=bool(pdf_ok), html=True, summary=True, lecture_title=title)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return bool(pdf_ok)
