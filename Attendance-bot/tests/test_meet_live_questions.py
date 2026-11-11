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
                "student": {"name": "Saad Naeem", "urdu_names": []},
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
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem, can you answer?")])
            await self.handler._question_answer_task

        self.assertIn("What is slope?", answer.call_args.args[2])
        send.assert_awaited_once_with("Slope is rise divided by run.")

    async def test_name_followed_by_question_is_answered_in_meeting_chat(self):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="test-key"),
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="Slope is rise divided by run."),
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True) as send,
        ):
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem")])
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem, what is slope?")])
            await self.handler._question_answer_task

        send.assert_awaited_once_with("Slope is rise divided by run.")

    async def test_name_mention_without_a_question_does_not_send_a_message(self):
        with patch.object(self.handler, "send_chat", new_callable=AsyncMock) as send:
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem is in class today.")])
            self.handler._check_for_addressed_question([("Teacher", "Saad Naeem can explain this topic.")])
            await asyncio.sleep(0)

        send.assert_not_awaited()

    async def test_microphone_or_playback_question_without_my_name_is_ignored(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._queue_whisper_speech("What is slope?", "playback")
            self.handler._queue_whisper_speech("What is slope?", "microphone")
            self.handler._record_whisper_transcripts()
            self.handler._handle_microphone_transcript("Ali, what is an algorithm?")

        queue_answer.assert_not_called()

    async def test_question_to_another_student_is_remembered_but_not_answered(self):
        self.handler.recorder = Mock()
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_question([("Teacher", "Ali, what is an algorithm?")])

        queue_answer.assert_not_called()
        self.handler.recorder.add_question.assert_called()

    async def test_my_full_name_on_microphone_or_playback_is_answered(self):
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._handle_microphone_transcript("Saad Naeem, what is slope?")

        queue_answer.assert_called_once_with("Saad Naeem, what is slope?")

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
                "Saad Naeem, what is slope?",
            ])
            self.handler._check_for_addressed_chat_questions([
                "old question from chat",
                "Saad Naeem, what is slope?",
            ])

        queue_answer.assert_called_once_with("Saad Naeem, what is slope?")

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

    def _page(self, **info):
        page = Mock()
        page.is_closed = Mock(return_value=False)
        page.evaluate = AsyncMock(return_value={"inCall": True, "text": "", "url": "", **info})
        self.handler.page = page

    async def test_low_participant_count_does_not_end_meeting(self):
        self._page(text="1 participant")
        self.assertFalse(await self.handler.is_meeting_ended())

    async def test_end_screen_ends_meeting_after_two_checks(self):
        self.handler._was_in_call = True
        self._page(inCall=False, text="the meeting has ended")
        self.assertFalse(await self.handler.is_meeting_ended())
        self.handler._end_checked_at = 0
        self.assertTrue(await self.handler.is_meeting_ended())

    async def _run_checks(self, n, **info):
        self._page(**info)
        result = False
        for _ in range(n):
            self.handler._end_checked_at = 0
            result = await self.handler.is_meeting_ended()
        return result

    async def test_unknown_end_screen_still_ends_after_several_checks(self):
        self.handler._was_in_call = True
        self.assertFalse(await self._run_checks(3, inCall=False, text="something new"))
        self.assertTrue(await self._run_checks(1, inCall=False, text="something new"))

    async def test_lobby_and_offline_do_not_end_meeting(self):
        self.handler._was_in_call = True
        self.assertFalse(await self._run_checks(6, inCall=False, text="asking to be let in"))
        self.assertFalse(await self._run_checks(6, inCall=False, text="x", online=False))

    async def test_never_joined_call_is_not_ended(self):
        self.assertFalse(await self._run_checks(6, inCall=False, text="the meeting has ended"))

    async def test_chat_text_does_not_end_meeting_while_in_call(self):
        self._page(inCall=True, text="sir the meeting has ended?")
        for _ in range(3):
            self.handler._end_checked_at = 0
            self.assertFalse(await self.handler.is_meeting_ended())

    async def test_bot_alone_after_lecture_ends_meeting(self):
        self._page(text="you're the only one here")
        self.handler.recorder = Mock(segments=[object()])
        self.handler.settings = {"end_when_alone_secs": 0}
        self.handler._end_checked_at = 0
        self.assertTrue(await self.handler.is_meeting_ended())


if __name__ == "__main__":
    unittest.main()
