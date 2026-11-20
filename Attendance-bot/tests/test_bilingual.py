import asyncio
import unittest
from collections import deque
from unittest.mock import AsyncMock, patch

from core import config_store
from detection.attendance_detector import AttendanceDetector
from platforms.meet_handler import MeetHandler
from utils import ai_notes
from utils.lang_utils import detect_language, normalize_urdu, reply_style


class LanguageDetectionTests(unittest.TestCase):
    def test_detects_each_language(self):
        self.assertEqual(detect_language("What is slope?"), "english")
        self.assertEqual(detect_language("آپ کیسے ہیں"), "urdu")
        self.assertEqual(detect_language("tum kese ho"), "roman_urdu")
        self.assertEqual(detect_language("Yes sir"), "english")

    def test_mixed_speech_is_detected_by_its_dominant_style(self):
        self.assertEqual(detect_language("slope کیا ہوتا ہے"), "urdu")
        self.assertEqual(detect_language("Python mein variable kya hota hai"), "roman_urdu")
        self.assertEqual(detect_language("Explain karo OOP"), "roman_urdu")

    def test_reply_follows_question_unless_forced(self):
        self.assertIn("Roman Urdu", reply_style("tum kese ho"))
        self.assertIn("Gen-Z", reply_style("آپ کیسے ہیں"))
        self.assertIn("Gen-Z", reply_style("मुझे बताओ क्या है"))
        self.assertIn("English", reply_style("how are you"))
        self.assertIn("English", reply_style("tum kese ho", "English"))

    def test_normalize_folds_spelling_variants(self):
        self.assertEqual(normalize_urdu("کیسے"), normalize_urdu("کیسی"))
        self.assertEqual(normalize_urdu("سَعد"), normalize_urdu("سعد"))


class UrduNameTests(unittest.TestCase):
    def setUp(self):
        self.d = AttendanceDetector({"student": {"name": "Saad Naeem", "urdu_names": []}})

    def test_spelling_variants_of_my_urdu_name_match(self):
        for text in ["ساد نعیم آپ کیسے ہیں", "سَعد نعیم بتائیں", "सआद नईम क्या है"]:
            self.assertTrue(self.d.is_addressed(text), text)

    def test_other_students_do_not_match(self):
        for text in ["سعد نعمان کیسے ہیں", "علی نعیم", "سعد احمد", "Saad Nadeem how are you"]:
            self.assertFalse(self.d.is_addressed(text), text)


class BilingualQuestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = MeetHandler(
            {"subject": "Math"},
            {
                "student": {"name": "Saad Naeem", "urdu_names": ["سعد نعیم"]},
                "global_settings": {},
                "features": {},
                "ai": {"provider": "gemini", "keys": {"gemini": "test-key"}},
            },
        )
        self.handler.captions = deque(["Lecture."], maxlen=50)

    async def _ask(self, line, extra=None):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="ok") as answer,
            patch("platforms.meet_handler.ai_notes.extract_addressed_question", return_value="") as extract,
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True),
        ):
            for text in [line] + list(extra or []):
                self.handler._check_for_addressed_question([("Teacher", text)])
            if self.handler._question_answer_task:
                await self.handler._question_answer_task
        return answer, extract

    async def test_roman_urdu_question_is_answered(self):
        answer, _ = await self._ask("Saad Naeem tum kese ho")
        self.assertEqual(answer.call_args.args[2], "Saad Naeem tum kese ho")

    async def test_urdu_script_question_without_question_mark_is_answered(self):
        answer, _ = await self._ask("سعد نعیم آپ کیسے ہیں")
        answer.assert_called_once()

    async def test_urdu_question_after_name_is_answered(self):
        answer, _ = await self._ask("سعد نعیم", ["slope کیا ہوتا ہے"])
        self.assertIn("slope", answer.call_args.args[2])

    async def test_mixed_english_urdu_question_is_answered(self):
        answer, _ = await self._ask("Saad Naeem, algorithm ka time complexity kya hoti hai")
        answer.assert_called_once()

    async def test_other_student_urdu_question_is_not_answered(self):
        answer, _ = await self._ask("علی آپ کیسے ہیں")
        answer.assert_not_called()

    async def test_ai_fallback_catches_phrasing_the_word_lists_miss(self):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch("platforms.meet_handler.ai_notes.extract_addressed_question",
                  return_value="Is lecture ki samajh aayi?") as extract,
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="Ji sir") as answer,
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True) as send,
        ):
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem is lecture par apna khayal dein")])
            await self.handler._ai_check_task
            await self.handler._question_answer_task
        extract.assert_called_once()
        self.assertEqual(answer.call_args.args[2], "Is lecture ki samajh aayi?")
        send.assert_awaited_once_with("Ji sir")

    async def test_roll_call_alone_never_calls_the_ai(self):
        answer, extract = await self._ask("Saad Naeem")
        extract.assert_not_called()
        answer.assert_not_called()


class ReplyLanguagePromptTests(unittest.TestCase):
    def _prompt(self, question, features=None):
        cfg = {"features": features or {}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}
        with patch("utils.ai_notes._call", return_value='{"answer": "ok"}') as call:
            ai_notes.answer_question(cfg, "ctx", question, None, True)
        return call.call_args.args[1] + call.call_args.kwargs["system"]

    def test_roman_urdu_question_gets_roman_urdu_instruction(self):
        self.assertIn("Roman Urdu", self._prompt("tum kese ho"))

    def test_english_question_gets_english_instruction(self):
        self.assertIn("clear, simple English", self._prompt("What is slope?"))

    def test_forced_reply_language_wins(self):
        self.assertIn("Urdu script", self._prompt("What is slope?", {"reply_language": "Urdu"}))


class ReplyLanguageSettingTests(unittest.TestCase):
    def test_default_is_auto_and_values_are_validated(self):
        self.assertEqual(config_store.DEFAULT_FEATURES["reply_language"], "auto")
        self.assertIn("Roman Urdu", config_store.REPLY_LANGS)


if __name__ == "__main__":
    unittest.main()
