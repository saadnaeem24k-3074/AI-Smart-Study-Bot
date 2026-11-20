import asyncio
import json
import time
import unittest
from collections import deque
from unittest.mock import AsyncMock, Mock, patch

from detection.attendance_detector import AttendanceDetector
from platforms.meet_handler import MeetHandler
from utils import ai_notes, pdf_builder
from utils.lang_utils import reply_style


def make_handler():
    return MeetHandler(
        {"subject": "SQE"},
        {"student": {"name": "Saad Naeem", "roll_no": "24K-3074", "urdu_names": []},
         "global_settings": {}, "features": {},
         "ai": {"provider": "gemini", "keys": {"gemini": "k"}}},
    )


class AttendanceKeywordTests(unittest.TestCase):
    def test_keyword_in_every_language(self):
        for text in ["now I am going to take attendance", "roll call time", "आज की अटेंडेंस लगाते हैं",
                     "آج حاضری لگاتے ہیں", "hazri laga lete hain", "اٹینڈنس مارک کر رہا ہوں"]:
            self.assertTrue(AttendanceDetector.is_attendance_keyword(text), text)
        self.assertFalse(AttendanceDetector.is_attendance_keyword("The attendances were recorded"))

    def test_roll_number_inside_a_question_is_not_a_roll_call(self):
        d = AttendanceDetector({"student": {"urdu_names": []}})
        self.assertEqual(d.analyze("24K3074 why do we need algorithms?"), "nothing")
        d.reset()
        self.assertEqual(d.analyze("24K3074"), "mark_present")


class AttendanceFromSpeechTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.h = make_handler()
        patcher = patch("platforms.meet_handler.ai_notes.api_key", return_value="")   # never hit the network
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_keyword_asks_for_present(self):
        self.h._process_sentence("Now I am going to take attendance")
        self.assertEqual(self.h._present_request["how"], "Attendance keyword")
        self.assertGreater(self.h._attendance_mode_until, time.time())

    def test_my_name_called_during_attendance_is_present_even_after_marking(self):
        self.h._attendance_marked = True
        self.h._attendance_mode_until = time.time() + 300
        self.h._process_sentence("24K3074")
        self.assertTrue(self.h._present_request["explicit"])
        self.assertEqual(self.h._present_request["delay"], 0.0)

    async def test_bare_call_before_attendance_waits_a_moment_for_a_question(self):
        self.h._process_sentence("24K3074")
        self.assertEqual(self.h._present_request["delay"], 4.0)
        with patch("platforms.meet_handler.ai_notes.api_key", return_value="k"), \
             patch("platforms.meet_handler.ai_notes.answer_question", return_value="ok"), \
             patch.object(self.h, "send_chat", new_callable=AsyncMock, return_value=True):
            self.h._process_sentence("24K3074 what is a graph?")
        self.assertIsNone(self.h._present_request)             # it was a question, not a roll call

    async def test_name_inside_a_question_is_not_attendance(self):
        with patch("platforms.meet_handler.ai_notes.api_key", return_value=""):
            self.h._process_sentence("24K3074 what is polymorphism")
        self.assertIsNone(self.h._present_request)

    async def test_request_is_sent_once_and_never_again_after_marked(self):
        state = Mock()
        state.get.return_value = False
        tg = Mock()
        with patch.object(self.h, "send_chat", new_callable=AsyncMock, return_value=True) as send:
            self.h._present_request = {"how": "Attendance keyword", "at": time.time() - 1, "delay": 0.0, "explicit": False}
            await self.h._handle_present_request(tg, {"subject": "SQE"}, state)
            send.assert_awaited_once_with("Present Sir")
            state.mark_attendance.assert_called_once()
            state.get.return_value = True                       # now marked
            self.h._present_request = {"how": "Attendance keyword", "at": time.time() - 1, "delay": 0.0, "explicit": False}
            await self.h._handle_present_request(tg, {}, state)
            self.assertEqual(send.await_count, 1)               # keyword alone: nothing more
            self.h._last_present_sent = time.time() - 60
            self.h._present_request = {"how": "Called", "at": time.time() - 1, "delay": 0.0, "explicit": True}
            await self.h._handle_present_request(tg, {}, state)
            self.assertEqual(send.await_count, 1)               # already marked: never answers a roll call again


class StudyGuideFormatTests(unittest.TestCase):
    RAW = {
        "title": "Functional Testing", "subtitle": "BVA, ECT, Decision tables",
        "covers": ["BVA and 4n + 1"],
        "sections": [{
            "heading": "Boundary Value Analysis", "key_idea": "Edges fail most.",
            "intro": ["BVA tests the edges."],
            "subsections": [{"heading": "Five values", "paragraphs": ["p"],
                             "tables": [{"headers": ["Value", "x"], "rows": [["Min", "1"], ["Max", "100"]]}],
                             "callouts": [{"kind": "Exam tip", "text": "n = number of inputs"}]}],
            "worked_examples": [{"title": "Square", "body": "x squared",
                                 "table": {"headers": ["x", "out"], "rows": [["2", "4"]]}}],
            "callouts": [{"kind": "weird kind", "text": "careful"}],
        }],
        "quick_reference": [{"title": "Formulas", "headers": ["Technique", "Count"], "rows": [["BVA", "4n+1"]]}],
        "exam_questions": ["Explain BVA."], "quiz": [],
    }

    def _notes(self):
        with patch("utils.ai_notes._call", return_value=json.dumps(self.RAW)):
            return asyncio.run(ai_notes.summarize({"features": {}}, "transcript"))

    def test_prompt_asks_for_the_study_guide_format_and_no_statistics(self):
        with patch("utils.ai_notes._call", return_value=json.dumps(self.RAW)) as call:
            asyncio.run(ai_notes.summarize({"features": {}}, "transcript"))
        prompt = call.call_args.args[1]
        for needle in ("STUDY-GUIDE FORMAT", "Exam tip", "quick_reference", "exam_questions",
                       "Never include statistics", "Write ALL note content in English"):
            self.assertIn(needle, prompt)

    def test_new_fields_are_normalised(self):
        notes = self._notes()
        section = notes["sections"][0]
        self.assertEqual(notes["subtitle"], "BVA, ECT, Decision tables")
        self.assertEqual(section["subsections"][0]["tables"][0]["rows"][1], ["Max", "100"])
        self.assertEqual(section["callouts"][0]["kind"], "Note")          # unknown kind falls back
        self.assertEqual(section["worked_examples"][0]["table"]["headers"], ["x", "out"])
        self.assertEqual(notes["quick_reference"][0]["rows"], [["BVA", "4n+1"]])

    def test_broken_tables_are_dropped_not_crashed_on(self):
        self.assertIsNone(ai_notes._normalize_table({"headers": [], "rows": [["x"]]}))
        self.assertIsNone(ai_notes._normalize_table({"headers": ["a"], "rows": []}))
        self.assertEqual(ai_notes._normalize_table({"headers": ["a", "b"], "rows": [["1"]]})["rows"], [["1", ""]])

    def test_pdf_has_the_new_layout_and_no_statistics(self):
        notes = self._notes()
        html = pdf_builder.build_html({
            "subject": "x", "title": "Functional Testing", "date_str": "12 November 2026", "start_time": "",
            "end_time": "", "duration_s": 1300, "words": 537, "speakers": 2, "slides": [], "summary": notes,
            "flags": [], "class_questions": [], "keywords": [], "transcript": [], "ai_requested": True}, {})
        body = html.split("</style>")[1]
        for needle in ("What this document covers", 'class="callout"', "Exam tip:", 'class="tbl"',
                       "Quick reference", "Likely exam questions", "BVA, ECT, Decision tables", "Square"):
            self.assertIn(needle, body)
        for stat in ("537", "speaker", "21m", "1,300", "words"):
            self.assertNotIn(stat, body)


class HedgedLiveCallTests(unittest.TestCase):
    CFG = {"ai": {"provider": "gemini", "keys": {"gemini": "g", "groq": "q"}},
           "features": {"live_reply_provider": "auto"}}

    def test_fast_primary_never_calls_the_second_provider(self):
        calls = []

        def fake(config, *a, **k):
            calls.append(config["ai"]["provider"])
            return '{"answer": "ok"}'

        with patch("utils.ai_notes._call", side_effect=fake):
            self.assertEqual(ai_notes._call_live(self.CFG, "q", 50), '{"answer": "ok"}')
        self.assertEqual(calls, ["gemini"])

    def test_slow_primary_is_beaten_by_the_hedge(self):
        def fake(config, *a, **k):
            if config["ai"]["provider"] == "gemini":
                time.sleep(4)
                return "slow"
            return "fast"

        started = time.monotonic()
        with patch("utils.ai_notes._call", side_effect=fake):
            self.assertEqual(ai_notes._call_live(self.CFG, "q", 50), "fast")
        self.assertLess(time.monotonic() - started, 3.8)


class ReplyStyleTests(unittest.TestCase):
    def test_english_question_english_reply_urdu_question_genz_mix(self):
        self.assertIn("English", reply_style("What is slope?"))
        for q in ["tum kese ho", "آپ کیسے ہیں", "24K3074 मुझे बताओ क्या है"]:
            style = reply_style(q)
            self.assertIn("Gen-Z", style)
            self.assertIn("Sir samajh agaya hai, but how would we know", style)


if __name__ == "__main__":
    unittest.main()
