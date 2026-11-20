import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ai_notes, notes_recorder

CFG = {"features": {"notes_language": "Urdu"}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}


class EnglishOnlyNotesTests(unittest.TestCase):
    def test_notes_prompt_is_english_even_if_old_setting_says_urdu(self):
        system = ai_notes._system(CFG)
        self.assertIn("clear English", system)
        self.assertIn("write all output in clear English", system)

    def test_non_live_answers_are_english_too(self):
        with patch("utils.ai_notes._call", return_value='{"answer": "ok"}') as call:
            ai_notes.answer_question(CFG, "ctx", "ایمپی کیا ہے؟", None, False)
        self.assertIn("clear English", call.call_args.kwargs["system"])

    def test_urdu_hindi_and_roman_urdu_are_translated_english_is_untouched(self):
        texts = ["यह पूछा ओ कि अलगो र्धा म का मतलब क्या है", "What is slope?",
                 "P problems wo hain jo jaldi solve ho jate hain"]
        with patch("utils.ai_notes._call",
                   return_value='{"items": ["What is an algorithm?", "P problems are solved quickly."]}') as call:
            out = asyncio.run(ai_notes.to_english(CFG, texts, "lecture"))
        self.assertEqual(out, ["What is an algorithm?", "What is slope?", "P problems are solved quickly."])
        sent = call.call_args.args[1]
        self.assertNotIn("What is slope?", sent)           # English is never sent for translation

    def test_failure_keeps_the_originals(self):
        with patch("utils.ai_notes._call", return_value="not json"):
            out = asyncio.run(ai_notes.to_english(CFG, ["अलगो र्थम क्या है"]))
        self.assertEqual(out, ["अलगो र्थम क्या है"])


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        notes_recorder.NOTES_ROOT = notes_recorder.Path(self.tmp.name)
        self.r = notes_recorder.NotesRecorder({"subject": "AI"}, {"features": {"notes": True}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_scraped_chat_panel_is_not_stored_as_a_question(self):
        self.r.add_question("5:18 pm walaikum assalam. my name is 24k 3074 hover over a message to pin it keep keep pin message a")
        self.r.add_question("why do we need these algorithms?")
        self.assertEqual([q["text"] for q in self.r.questions], ["why do we need these algorithms?"])

    def test_same_question_heard_in_several_scripts_becomes_one_entry(self):
        qs = [
            {"time": "1", "text": "What is an algorithm?", "to_me": False, "bot_answer": ""},
            {"time": "2", "text": "what is an algorithm", "to_me": True, "bot_answer": "A set of steps."},
            {"time": "3", "text": "What is an NP-hard problem?", "to_me": False, "bot_answer": ""},
        ]
        merged = self.r._merge_questions(qs)
        self.assertEqual(len(merged), 2)
        self.assertTrue(merged[0]["to_me"])
        self.assertEqual(merged[0]["bot_answer"], "A set of steps.")


if __name__ == "__main__":
    unittest.main()
