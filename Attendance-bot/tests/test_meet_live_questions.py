import asyncio
import unittest
from collections import deque
from unittest.mock import AsyncMock, Mock, patch

from platforms.meet_handler import MeetHandler


class LiveQuestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = MeetHandler(
            {"subject": "Math"},
            {
                "student": {"urdu_names": []},
                "global_settings": {},
                "features": {},
                "ai": {"provider": "gemini", "keys": {"gemini": "test-key"}},
            },
        )
        self.handler.captions = deque(["The lecture covered slope."], maxlen=50)

    async def test_attendance_reply_is_present_sir(self):
        state = Mock()
        tg = Mock()
        with patch.object(
            self.handler, "send_chat", new_callable=AsyncMock, return_value=True
        ) as send:
            await self.handler._send_present(tg, self.handler.cls, state, "Roll call")

        send.assert_awaited_once_with("Present Sir")
        state.mark_attendance.assert_called_once_with()

    async def test_question_followed_by_name_is_answered_in_meeting_chat(self):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="Slope is rise divided by run.") as answer,
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True) as send,
        ):
            self.handler._check_for_addressed_question([("Teacher", "What is slope?")])
            self.handler._check_for_addressed_question([("Teacher", "Saad, can you answer?")])
            await self.handler._question_answer_task

        self.assertIn("What is slope?", answer.call_args.args[2])
        send.assert_awaited_once_with("Slope is rise divided by run.")

    async def test_name_followed_by_question_is_answered_in_meeting_chat(self):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="Slope is rise divided by run."),
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True) as send,
        ):
            self.handler._check_for_addressed_question([("Teacher", "Saad")])
            self.handler._check_for_addressed_question([("Teacher", "Saad, what is slope?")])
            await self.handler._question_answer_task

        send.assert_awaited_once_with("Slope is rise divided by run.")

    async def test_name_mention_without_a_question_does_not_send_a_message(self):
        with patch.object(self.handler, "send_chat", new_callable=AsyncMock) as send:
            self.handler._check_for_addressed_question([("Teacher", "Saad is in class today.")])
            self.handler._check_for_addressed_question([("Teacher", "Saad can explain this topic.")])
            await asyncio.sleep(0)

        send.assert_not_awaited()

    async def test_microphone_question_is_routed_but_playback_is_not(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._queue_whisper_speech("What is slope?", "playback")
            self.handler._queue_whisper_speech("What is slope?", "microphone")
            self.handler._record_whisper_transcripts()

        queue_answer.assert_called_once_with("What is slope?")

    async def test_microphone_question_without_punctuation_is_detected(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._handle_microphone_transcript("What is slope")

        queue_answer.assert_called_once_with("What is slope")

    async def test_live_question_is_answered_even_without_transcript_context(self):
        self.handler.captions.clear()
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch(
                "platforms.meet_handler.ai_notes.answer_question",
                return_value="A database organizes data.",
            ) as answer_question,
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True) as send,
        ):
            await self.handler._answer_live_question("What is a database?")

        self.assertEqual(answer_question.call_args.args[1], "")
        send.assert_awaited_once_with("A database organizes data.")

    async def test_roll_number_addressed_voice_question_is_answered(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_question([
                ("Teacher", "What is slope? Please answer, 24K3-074.")
            ])

        queue_answer.assert_called_once()
        self.assertIn("What is slope", queue_answer.call_args.args[0])

    async def test_new_chat_question_addressed_by_name_is_answered_once(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_chat_questions(["old question from chat"])
            self.handler._check_for_addressed_chat_questions([
                "old question from chat",
                "Saad, what is slope?",
            ])
            self.handler._check_for_addressed_chat_questions([
                "old question from chat",
                "Saad, what is slope?",
            ])

        queue_answer.assert_called_once_with("Saad, what is slope?")

    async def test_new_chat_question_addressed_by_alternate_roll_format_is_answered(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_chat_questions(["existing chat"])
            self.handler._check_for_addressed_chat_questions([
                "existing chat",
                "What is slope? 24K3-074",
            ])

        queue_answer.assert_called_once_with("What is slope? 24K3-074")

    async def test_addressed_question_is_processed_on_first_chat_read(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_chat_questions([
                "24K3-074, what is the derivative?"
            ])

        queue_answer.assert_called_once_with("24K3-074, what is the derivative?")

    async def test_low_participant_count_does_not_end_meeting(self):
        locator = Mock()
        locator.count = AsyncMock(return_value=0)
        self.handler.page = Mock()
        self.handler.page.locator = Mock(return_value=locator)
        self.handler.page.evaluate = AsyncMock(return_value=1)

        self.assertFalse(await self.handler.is_meeting_ended())
        self.handler.page.evaluate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
