"""'Regenerate notes' must keep the lecture's slides (and questions), not rebuild from the transcript alone."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import notes_recorder, notes_regenerate

CONFIG = {"features": {}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}
SUMMARY = {"title": "T", "summary": ["s"], "sections": [{"heading": "H", "key_idea": "", "bullets": ["b"],
           "steps": [], "diagrams": [], "equations": [], "examples": []}], "emphasis": [], "homework": [],
           "deadlines": [], "key_terms": [], "quiz": []}
LECTURE = [
    "The derivative measures the rate of change of a function at a point in time",
    "We compute it by taking the limit of the difference quotient as h goes to zero",
    "Now look at the second slide where we apply the power rule to polynomials",
    "The power rule says the derivative of x to the n is n times x to the n minus one",
]


def record(tmp, subject="Calculus", speakers=("Teacher", "Teacher")):
    """Record a small lecture exactly the way the bot does and return its folder."""
    with patch.object(notes_recorder, "NOTES_ROOT", Path(tmp) / "notes"):
        rec = notes_recorder.NotesRecorder(
            {"subject": subject}, {"features": {"notes": True, "ai_summary": False}})
        rec.slides_dir.mkdir(parents=True, exist_ok=True)
        for n, (first, second) in enumerate([LECTURE[:2], LECTURE[2:]], start=1):
            (rec.slides_dir / f"slide_{n:03d}.jpg").write_bytes(b"\xff\xd8fake")
            rec.add_slide(f"slides/slide_{n:03d}.jpg", "slide" if n == 1 else "moment")
            rec.feed([(speakers[0], first)])
            rec.feed([(speakers[1], second)])
        rec.add_question("What is the derivative of a constant function?", to_me=True, answer="It is zero.")
        rec.flush()
        rec._write_meta(done=True)
        # the real end-of-class file also carries the notes above the transcript
        (rec.dir / "transcript.md").write_text(rec._render_md(SUMMARY), encoding="utf-8")
        return rec.dir


class RegenerateKeepsSlidesTests(unittest.IsolatedAsyncioTestCase):
    async def run_regen(self, folder, instructions=""):
        slide_notes = AsyncMock(return_value={1: {"takeaway": "Derivative", "bullets": ["rate of change"]}})
        with patch.object(notes_regenerate.ai_notes, "summarize", new=AsyncMock(return_value=dict(SUMMARY))), \
             patch.object(notes_regenerate.ai_notes, "summarize_meeting", new=AsyncMock(return_value=dict(SUMMARY))) as meeting, \
             patch.object(notes_regenerate.ai_notes, "slide_notes", new=slide_notes), \
             patch.object(notes_regenerate.ai_notes, "to_english", new=AsyncMock(side_effect=lambda c, t, p: t)), \
             patch.object(notes_regenerate.ai_notes, "answer_class_questions",
                          new=AsyncMock(side_effect=lambda c, p, q: [""] * len(q))), \
             patch.object(notes_regenerate.pdf_builder, "render_pdf", new=AsyncMock(return_value=True)):
            ok = await notes_regenerate.regenerate(folder, CONFIG, instructions)
        return ok, slide_notes, meeting

    async def test_regenerated_notes_include_every_slide_and_its_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp)
            self.assertTrue((folder / "slides.json").is_file())
            ok, slide_notes, _ = await self.run_regen(folder)
            html = (folder / "notes.html").read_text(encoding="utf-8")
        self.assertTrue(ok)
        per_slide = slide_notes.call_args.args[1]
        self.assertEqual(sorted(per_slide), [1, 2])
        self.assertIn("derivative measures", per_slide[1])
        self.assertIn("power rule", per_slide[2])
        self.assertIn("slides/slide_001.jpg", html)
        self.assertIn("slides/slide_002.jpg", html)
        self.assertIn("Snapshot 2", html)                         # the second capture was a snapshot
        self.assertIn("Derivative", html)                         # the AI per-slide takeaway made it in

    async def test_folders_recorded_before_slides_json_existed_are_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp)
            (folder / "slides.json").unlink()
            ok, slide_notes, _ = await self.run_regen(folder)
            html = (folder / "notes.html").read_text(encoding="utf-8")
        self.assertTrue(ok)
        self.assertEqual(sorted(slide_notes.call_args.args[1]), [1, 2])
        self.assertIn("slides/slide_001.jpg", html)
        self.assertIn("slides/slide_002.jpg", html)

    async def test_questions_come_back_from_the_transcript_when_the_json_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp)
            (folder / "class_questions.json").unlink(missing_ok=True)
            await self.run_regen(folder)
            html = (folder / "notes.html").read_text(encoding="utf-8")
        self.assertIn("derivative of a constant function", html)
        self.assertIn("It is zero.", html)

    async def test_meeting_recordings_regenerate_as_speaker_attributed_minutes_with_slides(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp, subject="Meeting with friends", speakers=("Ali", "Sara"))
            ok, slide_notes, meeting = await self.run_regen(folder, "focus on decisions")
            html = (folder / "notes.html").read_text(encoding="utf-8")
        self.assertTrue(ok)
        plain = meeting.call_args.args[1]
        self.assertRegex(plain, r"\[\d\d:\d\d:\d\d\] Ali: ")
        self.assertRegex(plain, r"\[\d\d:\d\d:\d\d\] Sara: ")
        self.assertEqual(meeting.call_args.args[3], "focus on decisions")
        self.assertEqual(slide_notes.call_args.args[2], "discussed")
        self.assertIn("MEETING NOTES", html)
        self.assertIn("slides/slide_001.jpg", html)

    def test_assign_slides_by_time_for_transcripts_without_slide_markers(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 11, 25, 21, 0, 0, tzinfo=notes_recorder.PKT)
        seg = lambda minutes: notes_recorder.Segment("T", "x", base + timedelta(minutes=minutes))
        segments = [seg(0), seg(5), seg(11)]
        slides = [{"n": 1, "t": (base + timedelta(minutes=1)).timestamp()},
                  {"n": 2, "t": (base + timedelta(minutes=10)).timestamp()}]
        notes_regenerate.assign_slides_by_time(segments, slides)
        self.assertEqual([s.slide for s in segments], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()


class NotesScopeTests(RegenerateKeepsSlidesTests):
    """'Only what was discussed': nothing of the AI's own in the notes."""

    async def test_a_lecture_set_to_discussed_only_uses_the_strict_summarizer_and_adds_no_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp)                                   # a normal class recording
            cfg = {**CONFIG, "features": {"notes_scope": "discussed"}}
            answers = AsyncMock(side_effect=lambda c, p, q: ["AI wrote this"] * len(q))
            with patch.object(notes_regenerate.ai_notes, "summarize", new=AsyncMock()) as lecture, \
                 patch.object(notes_regenerate.ai_notes, "summarize_meeting", new=AsyncMock(return_value=dict(SUMMARY))) as strict, \
                 patch.object(notes_regenerate.ai_notes, "slide_notes", new=AsyncMock(return_value={})) as slide_notes, \
                 patch.object(notes_regenerate.ai_notes, "to_english", new=AsyncMock(side_effect=lambda c, t, p: t)), \
                 patch.object(notes_regenerate.ai_notes, "answer_class_questions", new=answers), \
                 patch.object(notes_regenerate.pdf_builder, "render_pdf", new=AsyncMock(return_value=True)):
                await notes_regenerate.regenerate(folder, cfg)
            html = (folder / "notes.html").read_text(encoding="utf-8")
        lecture.assert_not_called()
        strict.assert_called_once()
        answers.assert_not_called()                                 # no AI-written answers to the questions
        self.assertNotIn("AI wrote this", html)
        self.assertEqual(slide_notes.call_args.args[2], "discussed")
        self.assertIn("only what was said", html)
        self.assertIn("It is zero.", html)                          # what the bot really replied in chat stays

    async def test_study_scope_keeps_the_lecture_notes_for_a_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = record(tmp)
            cfg = {**CONFIG, "features": {"notes_scope": "study"}}
            with patch.object(notes_regenerate.ai_notes, "summarize", new=AsyncMock(return_value=dict(SUMMARY))) as lecture, \
                 patch.object(notes_regenerate.ai_notes, "summarize_meeting", new=AsyncMock()) as strict, \
                 patch.object(notes_regenerate.ai_notes, "slide_notes", new=AsyncMock(return_value={})), \
                 patch.object(notes_regenerate.ai_notes, "to_english", new=AsyncMock(side_effect=lambda c, t, p: t)), \
                 patch.object(notes_regenerate.ai_notes, "answer_class_questions",
                              new=AsyncMock(side_effect=lambda c, p, q: [""] * len(q))) as answers, \
                 patch.object(notes_regenerate.pdf_builder, "render_pdf", new=AsyncMock(return_value=True)):
                await notes_regenerate.regenerate(folder, cfg)
        lecture.assert_called_once()
        strict.assert_not_called()
        answers.assert_called_once()

    def test_scope_resolution(self):
        resolve = notes_recorder.resolve_notes_scope
        self.assertEqual(resolve("auto", "meeting"), "discussed")
        self.assertEqual(resolve("auto", "class"), "study")
        self.assertEqual(resolve("discussed", "class"), "discussed")
        self.assertEqual(resolve("study", "meeting"), "study")

    async def test_the_strict_prompt_forbids_additions_except_the_obvious_ones(self):
        from utils import ai_notes
        seen = {}
        def fake_call(cfg, prompt, tokens, *a, **k):
            seen["prompt"] = prompt
            return "{}"
        with patch.object(ai_notes, "_call", side_effect=fake_call):
            await ai_notes.summarize_meeting(CONFIG, "[21:04:39] Ali: hello there everyone", [])
        prompt = seen["prompt"]
        self.assertIn("Add nothing of your own", prompt)
        self.assertIn("so obvious", prompt)
        self.assertIn("(note: ...)", prompt)
        self.assertIn("EVERY bullet", prompt)

    # the inherited slide / question tests are re-run by the parent class; skip the duplicates here
    test_regenerated_notes_include_every_slide_and_its_screenshot = None
    test_folders_recorded_before_slides_json_existed_are_rebuilt = None
    test_questions_come_back_from_the_transcript_when_the_json_is_missing = None
    test_meeting_recordings_regenerate_as_speaker_attributed_minutes_with_slides = None
    test_assign_slides_by_time_for_transcripts_without_slide_markers = None
