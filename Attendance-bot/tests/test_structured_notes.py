import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import config_store
from utils import ai_notes, notes_recorder, pdf_builder


class ProviderRetryTests(unittest.TestCase):
    @patch("utils.ai_notes.requests.post")
    def test_retries_transient_connection_failure_once(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        post.side_effect = [ai_notes.requests.ConnectionError("temporary disconnect"), response]

        self.assertEqual(ai_notes._post("https://provider.invalid", {}, {}, "Test"), {"ok": True})
        self.assertEqual(post.call_count, 2)


class PdfSettingsTests(unittest.TestCase):
    @patch("core.config_store.save_raw")
    @patch("core.config_store.load_raw", return_value={"features": {}})
    def test_saves_pdf_preferences(self, _load, save):
        config_store.update_settings({"features": {
            "pdf_detail": "concise",
            "pdf_include_transcript": True,
            "pdf_paper_size": "Letter",
        }})

        self.assertEqual(save.call_args.args[0]["features"]["pdf_detail"], "concise")
        self.assertTrue(save.call_args.args[0]["features"]["pdf_include_transcript"])
        self.assertEqual(save.call_args.args[0]["features"]["pdf_paper_size"], "Letter")

    @patch("core.config_store.save_raw")
    @patch("core.config_store.load_raw", return_value={"features": {}})
    def test_rejects_unsupported_paper_size(self, _load, save):
        with self.assertRaises(ValueError):
            config_store.update_settings({"features": {"pdf_paper_size": "Legal"}})
        save.assert_not_called()


class StructuredNotesTests(unittest.IsolatedAsyncioTestCase):
    @patch("utils.ai_notes._call")
    async def test_generates_and_normalizes_structured_notes(self, call):
        call.return_value = json.dumps({
            "title": "Slope and equations of lines",
            "summary": ["Slope measures a line's rate of change."],
            "sections": [{
                "heading": "Slope",
                "key_idea": "Slope is rise over run.",
                "bullets": ["Compare the vertical and horizontal changes."],
                "equations": ["m = (y2 - y1) / (x2 - x1)"],
                "examples": ["For (3, 5) and (10, 10), m = 5/7."],
            }],
            "emphasis": [],
            "homework": [],
            "deadlines": [],
            "key_terms": ["slope"],
            "quiz": [],
        })
        config = {"features": {"pdf_detail": "detailed", "notes_language": "English"}}

        notes = await ai_notes.summarize(config, "Transcript about slope.")

        self.assertEqual(notes["sections"][0]["heading"], "Slope")
        self.assertEqual(notes["sections"][0]["equations"], ["m = (y2 - y1) / (x2 - x1)"])
        self.assertIn("Do not simply repeat", call.call_args.args[1])
        self.assertIn("Transcript about slope.", call.call_args.args[1])
        self.assertEqual(call.call_args.args[2], 7000)

    @patch("utils.ai_notes._call")
    async def test_concise_setting_changes_requested_output_length(self, call):
        call.return_value = json.dumps({"title": "Short", "sections": []})

        await ai_notes.summarize({"features": {"pdf_detail": "concise"}}, "Short transcript.")

        self.assertEqual(call.call_args.args[2], 4500)

    @patch("utils.ai_notes._call")
    async def test_corrects_spelling_and_preserves_transcript_metadata(self, call):
        call.return_value = json.dumps({
            "segments": [{"id": 0, "text": "Software testing checks for errors and bugs."}]
        })
        segments = [{
            "time": "22:35:00",
            "speaker": "Teacher",
            "text": "Software testin checks for erors and bugs.",
        }]

        corrected = await ai_notes.correct_transcript(
            {"ai": {"provider": "gemini"}, "features": {}}, segments)

        self.assertEqual(corrected[0]["text"], "Software testing checks for errors and bugs.")
        self.assertEqual(corrected[0]["time"], segments[0]["time"])
        self.assertEqual(corrected[0]["speaker"], segments[0]["speaker"])
        self.assertIn("Do not summarize, omit, reorder, translate, or add facts", call.call_args.args[1])

    @patch("utils.ai_notes._call")
    async def test_keeps_original_when_ai_drops_a_segment(self, call):
        call.return_value = json.dumps({"segments": []})

        corrected = await ai_notes.correct_transcript(
            {"ai": {"provider": "gemini"}, "features": {}},
            [{"time": "22:35:00", "speaker": "Teacher", "text": "Original caption."}])

        self.assertIsNone(corrected)


class StudyNotesPdfTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "subject": "Calculus",
            "date_str": "Thursday, 22 October 2026 · 21:00",
            "duration_s": 120,
            "words": 40,
            "speakers": 1,
            "end_time": "21:02:00",
            "summary": {
                "title": "Slope and equations of lines",
                "summary": ["Slope is the rate of change of a line."],
                "sections": [{
                    "heading": "Finding the slope",
                    "key_idea": "Slope equals rise divided by run.",
                    "bullets": ["Use two distinct points on the line."],
                    "equations": ["m = (y2 - y1) / (x2 - x1)"],
                    "examples": ["The points (3, 5) and (10, 10) give m = 5/7."],
                }],
            },
            "transcript": [("21:00", [("21:00:01", "Teacher", "Raw caption text.")])],
        }

    def test_pdf_html_renders_ai_notes_and_omits_transcript_by_default(self):
        rendered = pdf_builder.build_html(self.context)

        self.assertIn("Organized study notes", rendered)
        self.assertIn("Finding the slope", rendered)
        self.assertIn("m = (y2 - y1) / (x2 - x1)", rendered)
        self.assertNotIn("Full transcript", rendered)
        self.assertNotIn("Raw caption text.", rendered)

    def test_transcript_appendix_can_be_enabled(self):
        rendered = pdf_builder.build_html(self.context, {"include_transcript": True})

        self.assertIn("Full transcript", rendered)
        self.assertIn("Raw caption text.", rendered)


class NotesRecorderCleanupTests(unittest.IsolatedAsyncioTestCase):
    @patch("utils.notes_recorder.ai_notes.api_key", return_value="configured")
    @patch("utils.notes_recorder.ai_notes.correct_transcript")
    @patch("utils.notes_recorder.ai_notes.summarize")
    @patch("utils.notes_recorder.pdf_builder.build_html", return_value="<html></html>")
    @patch("utils.notes_recorder.pdf_builder.render_pdf")
    async def test_keeps_raw_and_saves_corrected_transcript(
        self, render_pdf, _build_html, summarize, correct, _api_key
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "notes"
            correct.return_value = [{
                "time": "22:35:01",
                "speaker": "Teacher",
                "text": "Software testing checks for errors and bugs.",
            }]
            summarize.return_value = {
                "title": "Software testing",
                "summary": ["Testing finds software defects."],
                "sections": [],
                "emphasis": [],
                "homework": [],
                "deadlines": [],
                "key_terms": [],
                "quiz": [],
            }
            render_pdf.return_value = True
            config = {
                "features": {"notes": True, "ai_summary": True, "slides": False},
                "ai": {"provider": "gemini"},
            }
            with patch("utils.notes_recorder.NOTES_ROOT", root):
                recorder = notes_recorder.NotesRecorder({"subject": "Software"}, config)
                recorder.feed([("Teacher", "Software testin checks for erors and bugs.")])

                await recorder.finalize()

            folder = next(root.glob("Software/*"))
            original = (folder / "transcript.md").read_text(encoding="utf-8")
            cleaned = (folder / "transcript_corrected.md").read_text(encoding="utf-8")
            self.assertIn("Software testin checks for erors and bugs.", original)
            self.assertIn("Software testing checks for errors and bugs.", cleaned)
            self.assertNotIn("Software testin checks for erors and bugs.", cleaned)
            self.assertIn("Software testing checks for errors and bugs.", summarize.call_args.args[1])
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            self.assertTrue(meta["corrected_transcript"])


if __name__ == "__main__":
    unittest.main()
