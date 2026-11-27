"""
Regression tests for the problems seen when the bot was tried in a real meeting with friends:

  1. it answered questions nobody asked it (treated as "follow-ups"),
  2. it answered when its name was only MENTIONED ("Saad Naeem gave a good answer"),
  3. it could not tell speakers apart,
  4. its notes did not follow what was actually said.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection import addressing
from detection.attendance_detector import AttendanceDetector
from platforms.meet_handler import MeetHandler
from utils import ai_notes, notes_recorder
from utils.speakers import SpeakerTracker

CONFIG = {
    "student": {"name": "Saad Naeem", "roll_no": "24K-3074", "urdu_names": ["سعد نعیم"]},
    "global_settings": {},
    "features": {},
    "ai": {"provider": "gemini", "keys": {"gemini": "test-key"}},
}


def make_handler():
    handler = MeetHandler({"subject": "Meeting with friends"}, CONFIG)
    handler.speakers.observe("Ali")
    handler.speakers.observe("Sara")
    return handler


class MentionRoleTests(unittest.TestCase):
    def setUp(self):
        self.detector = AttendanceDetector(CONFIG)

    def role(self, text):
        return self.detector.mention_verdict(text).role

    def test_being_spoken_to(self):
        for text in [
            "Saad Naeem, what is an NP problem?",
            "24K3074 what is a database",
            "What is slope? Please answer, 24K3-074.",
            "alright 24k3074 bataiye np hard kya hota hai",
            "سعد نعیم آپ کیسے ہیں",
        ]:
            self.assertEqual(self.role(text), addressing.ADDRESS, text)

    def test_being_spoken_about_is_never_a_call_on(self):
        for text in [
            "Saad Naeem or 24K-3074 gave a good answer",
            "Did Saad Naeem answer correctly?",
            "Thanks to Saad Naeem for the answer",
            "Ask Saad Naeem what is NP",
            "Saad Naeem's answer was right",
            "Saad Naeem ne bataya tha",
            "Is 24K3074 absent today?",
        ]:
            self.assertEqual(self.role(text), addressing.REFERENCE, text)

    def test_unclear_cases_are_left_to_the_judge(self):
        for text in ["I think Saad Naeem what is NP is tricky", "Saad Naeem can explain this topic."]:
            self.assertEqual(self.role(text), addressing.AMBIGUOUS, text)

    def test_roll_call_wording_still_marks_attendance(self):
        self.assertEqual(self.detector.analyze("My roll number is 24K-3074"), "mark_present")

    def test_a_roll_number_only_talked_about_is_not_a_roll_call(self):
        self.assertEqual(AttendanceDetector(CONFIG).analyze("24K3074 gave a good answer"), "nothing")


class BotInAFriendsMeetingTests(unittest.IsolatedAsyncioTestCase):
    """Several people talking; the bot must only react when it is genuinely spoken to."""

    def setUp(self):
        self.h = make_handler()
        self.queued = []
        self.judge = patch(
            "platforms.meet_handler.ai_notes.extract_addressed_question", return_value="").start()
        patch("platforms.meet_handler.ai_notes.api_key", return_value="k").start()
        patch.object(self.h, "_queue_live_answer", side_effect=self.queued.append).start()
        self.addCleanup(patch.stopall)

    async def say(self, speaker, text):
        self.h._process_sentence(text, speaker)
        for task in (self.h._ai_check_task,):
            if task:
                await task

    async def test_mention_without_a_call_does_not_open_a_follow_up_window(self):
        # the exact failure from the test: name used in praise, next question belongs to someone else
        await self.say("Ali", "Saad Naeem or 24K-3074 gave a good answer")
        await self.say("Sara", "What is a database?")
        self.assertEqual(self.queued, [])

    async def test_question_directly_to_me_is_answered(self):
        await self.say("Ali", "Saad Naeem, what is an NP problem?")
        self.assertEqual(self.queued, ["Saad Naeem, what is an NP problem?"])

    async def test_someone_elses_question_after_my_call_is_not_a_follow_up(self):
        await self.say("Ali", "Saad Naeem")                       # bare call-on, waiting for the question
        await self.say("Sara", "What is a database?")             # a different person asks something else
        self.assertEqual(self.queued, [])

    async def test_same_person_finishing_the_question_is_answered(self):
        await self.say("Ali", "Saad Naeem")
        await self.say("Ali", "What is a database?")
        self.assertEqual(self.queued, ["What is a database?"])

    async def test_question_for_another_person_closes_the_conversation(self):
        await self.say("Ali", "Saad Naeem")
        await self.say("Ali", "Sara, what is a graph?")
        await self.say("Ali", "What is a tree?")
        self.assertEqual(self.queued, [])

    async def test_follow_up_count_is_limited(self):
        await self.say("Ali", "Saad Naeem, what is a database?")
        self.queued.clear()
        for question in ["And what is a table?", "And what is a key?", "And what is an index?"]:
            await self.say("Ali", question)
        self.assertEqual(self.queued, ["And what is a table?", "And what is a key?"])

    async def test_unknown_speaker_needs_a_clear_continuation(self):
        await self.say("", "Saad Naeem")
        await self.say("", "What is the capital of France?")      # unrelated: not a follow-up
        self.assertEqual(self.queued, [])
        self.judge.assert_called()                                # the judge is asked instead of guessing

    async def test_my_own_voice_never_triggers_the_bot(self):
        await self.say("You", "Saad Naeem, what is an NP problem?")
        self.assertEqual(self.queued, [])

    async def test_ambiguous_mention_goes_to_the_judge_with_speaker_labelled_context(self):
        self.judge.return_value = ""
        await self.say("Ali", "Okay we will see")
        await self.say("Sara", "I think Saad Naeem what is NP is tricky")
        self.judge.assert_called_once()
        lines = self.judge.call_args.args[1]
        self.assertTrue(any(line.startswith("Sara: ") for line in lines))
        self.assertEqual(self.judge.call_args.kwargs["asker"], "Sara")
        self.assertIn("Ali", self.judge.call_args.kwargs["roster"])
        self.assertEqual(self.queued, [])

    async def test_judge_can_confirm_an_ambiguous_call(self):
        self.judge.return_value = "What is NP?"
        await self.say("Ali", "I think Saad Naeem what is NP is tricky")
        self.assertEqual(self.queued, ["What is NP?"])

    async def test_a_reference_never_reaches_the_judge(self):
        await self.say("Ali", "Did Saad Naeem answer that correctly?")
        self.judge.assert_not_called()
        self.assertEqual(self.queued, [])

    async def test_questions_are_still_remembered_for_the_notes(self):
        from unittest.mock import Mock
        self.h.recorder = Mock()
        await self.say("Sara", "Ali, what is an algorithm?")
        self.h.recorder.add_question.assert_called()
        self.assertEqual(self.queued, [])


class SpeakerTrackerTests(unittest.TestCase):
    def test_active_speaker_and_overlap(self):
        tracker = SpeakerTracker(["Saad Naeem"])
        for _ in range(4):
            tracker.observe("Ali", now=100.0)
        self.assertEqual(tracker.active_speaker(now=102.0), "Ali")
        for _ in range(4):
            tracker.observe("Sara", now=101.0)
        self.assertEqual(tracker.active_speaker(now=102.0), "")      # overlap: refuse to guess
        self.assertEqual(tracker.active_speaker(now=500.0), "")      # nobody recently

    def test_roster_excludes_me(self):
        tracker = SpeakerTracker(["Saad Naeem"])
        for name in ("You", "Saad Naeem", "Ali"):
            tracker.observe(name)
        self.assertEqual(tracker.names(), ["Ali"])
        self.assertTrue(tracker.is_self("You"))


class MeetingNotesRecorderTests(unittest.TestCase):
    def recorder(self, tmp, subject="Meeting with friends", **features):
        patcher = patch.object(notes_recorder, "NOTES_ROOT", Path(tmp) / "notes")
        patcher.start()
        self.addCleanup(patcher.stop)
        return notes_recorder.NotesRecorder(
            {"subject": subject}, {"features": {"notes": True, "ai_summary": True, **features},
                                   "ai": {"provider": "gemini", "keys": {"gemini": "k"}}})

    def test_interleaved_speakers_stay_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = self.recorder(tmp)
            rec.feed([("Ali", "I think the bot should only listen when called by name")])
            rec.feed([("Sara", "Agreed.")])
            rec.feed([("Ali", "I think the bot should only listen when called by name and roll number")])
        self.assertEqual([s.speaker for s in rec.segments], ["Ali", "Sara", "Ali"])
        self.assertEqual(rec.segments[2].text, "and roll number")

    def test_audio_is_attributed_to_the_active_speaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = self.recorder(tmp)
            rec.add_audio_transcript("Now we compare the two approaches in detail today.", "Ali")
            rec.add_audio_transcript("Something nobody could attribute to anyone here.")
        self.assertEqual(rec.segments[0].speaker, "Ali")
        self.assertEqual(rec.segments[1].speaker, notes_recorder.UNATTRIBUTED)

    def test_mode_detection(self):
        seg = lambda who, n: notes_recorder.Segment(who, "word " * n, notes_recorder.datetime.now())
        peers = [seg("Ali", 80), seg("Sara", 70), seg("Bilal", 60)]
        teacher = [seg("Teacher", 400), seg("Student", 30)]
        self.assertEqual(notes_recorder.detect_session_mode("Algorithms", peers), "meeting")
        self.assertEqual(notes_recorder.detect_session_mode("Algorithms", teacher), "class")
        self.assertEqual(notes_recorder.detect_session_mode("Meeting with boiz", teacher), "meeting")
        self.assertEqual(notes_recorder.detect_session_mode("Meeting with boiz", peers, "class"), "class")


class MeetingNotesPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_uses_speaker_attributed_meeting_summary(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(notes_recorder, "NOTES_ROOT", Path(tmp) / "notes"), \
                patch.object(notes_recorder.ai_notes, "api_key", return_value="k"), \
                patch.object(notes_recorder.ai_notes, "correct_transcript", new=AsyncMock(return_value=None)), \
                patch.object(notes_recorder.ai_notes, "summarize", new=AsyncMock()) as lecture, \
                patch.object(notes_recorder.ai_notes, "summarize_meeting", new=AsyncMock(return_value=None)) as meeting, \
                patch.object(notes_recorder.pdf_builder, "render_pdf", new=AsyncMock(return_value=False)):
            rec = notes_recorder.NotesRecorder(
                {"subject": "Meeting with friends"},
                {"features": {"notes": True, "ai_summary": True}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}})
            rec.feed([("Ali", "The bot keeps answering questions that were not for it")])
            rec.feed([("Sara", "We should make it listen only when its name is called")])
            await rec.finalize()
        lecture.assert_not_called()
        plain = meeting.call_args.args[1]
        self.assertIn("Ali: The bot keeps answering", plain)
        self.assertIn("Sara: We should make it listen", plain)
        self.assertRegex(plain, r"^\[\d\d:\d\d:\d\d\] Ali:")
        speakers = {row["speaker"] for row in meeting.call_args.args[2]}
        self.assertEqual(speakers, {"Ali", "Sara"})


class GroundingTests(unittest.IsolatedAsyncioTestCase):
    PLAIN = "[21:04:39] Ali: what is NP\n[21:04:50] Sara: a class of problems\n"

    def test_statements_without_a_real_timestamp_are_dropped(self):
        notes = {
            "title": "t", "summary": [], "emphasis": ["Sara explained NP [21:04:50]", "Invented decision [22:30:00]"],
            "homework": ["Ali: write tests"], "deadlines": [], "open_questions": [],
            "sections": [{"heading": "NP", "key_idea": "", "steps": [], "diagrams": [], "equations": [], "examples": [],
                          "bullets": ["Ali asked what NP is [21:04:39]", "Made up fact", "Made up time [21:59:59]"]}],
            "by_speaker": [{"speaker": "Ali", "points": ["Asked about NP [21:04:39]", "No citation"]}],
        }
        out = ai_notes.ground_meeting_notes(notes, self.PLAIN)
        self.assertEqual(out["sections"][0]["bullets"], ["Ali asked what NP is [21:04:39]"])
        self.assertEqual(out["emphasis"], ["Sara explained NP [21:04:50]"])
        self.assertEqual(out["homework"], [])
        self.assertEqual(out["by_speaker"][0]["points"], ["Asked about NP [21:04:39]"])

    def test_fully_invented_notes_are_rejected(self):
        notes = {"summary": [], "emphasis": [], "homework": [], "deadlines": [], "open_questions": [],
                 "sections": [{"heading": "x", "key_idea": "", "bullets": ["no time"]}], "by_speaker": []}
        self.assertIsNone(ai_notes.ground_meeting_notes(notes, self.PLAIN))

    async def test_summarize_meeting_end_to_end_drops_ungrounded_lines(self):
        reply = json.dumps({
            "title": "Bot test", "subtitle": "bot",
            "summary": ["They tested the bot. [21:04:39]", "Then they flew to the moon."],
            "sections": [{"heading": "Testing", "key_idea": "bot answers", "bullets": [
                "Ali asked what NP is [21:04:39]", "Textbook: NP stands for nondeterministic polynomial time."]}],
            "decisions": [], "action_items": [{"item": "limit scope", "owner": "Saad", "when": "", "at": "[21:04:50]"}],
            "open_questions": [], "by_speaker": [], "key_terms": []})
        cfg = {"features": {}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}
        with patch.object(ai_notes, "_call", return_value=reply):
            notes = await ai_notes.summarize_meeting(cfg, self.PLAIN, [{"speaker": "Ali", "turns": 1, "words": 3}])
        self.assertEqual(notes["summary"], ["They tested the bot. [21:04:39]"])
        self.assertEqual(notes["sections"][0]["bullets"], ["Ali asked what NP is [21:04:39]"])
        self.assertEqual(notes["homework"], ["Saad: limit scope [21:04:50]"])
        self.assertEqual(notes["quiz"], [])


class JudgeReplyParsingTests(unittest.TestCase):
    CFG = {"features": {}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}

    def judge(self, reply):
        with patch.object(ai_notes, "_call_live", return_value=json.dumps(reply)):
            return ai_notes.extract_addressed_question(self.CFG, ["Ali: hello", "Ali: Saad Naeem what is NP"], "Saad Naeem")

    def test_only_a_confident_asked_me_verdict_returns_a_question(self):
        self.assertEqual(self.judge({"relation": "asked_me", "confidence": 0.9, "question": "what is NP"}), "what is NP")
        self.assertEqual(self.judge({"relation": "asked_me", "confidence": 0.5, "question": "what is NP"}), "")
        self.assertEqual(self.judge({"relation": "about_me", "confidence": 0.99, "question": "what is NP"}), "")
        self.assertEqual(self.judge({"relation": "for_someone_else", "confidence": 0.99, "question": "x"}), "")
        self.assertEqual(self.judge({"relation": "no_question", "confidence": 1, "question": ""}), "")

    def test_garbage_fails_closed(self):
        with patch.object(ai_notes, "_call_live", return_value="not json at all"):
            self.assertEqual(ai_notes.extract_addressed_question(self.CFG, ["Ali: hi"], "Saad"), "")
        with patch.object(ai_notes, "_call_live", return_value=None):
            self.assertEqual(ai_notes.extract_addressed_question(self.CFG, ["Ali: hi"], "Saad"), "")


if __name__ == "__main__":
    unittest.main()


class RepliesDisabledTests(unittest.IsolatedAsyncioTestCase):
    """Settings -> 'Reply in chat to questions' off: no replies, but attendance still works."""

    def setUp(self):
        self.h = make_handler()
        self.h.features["answer_questions"] = False
        patch("platforms.meet_handler.ai_notes.api_key", return_value="k").start()
        self.judge = patch("platforms.meet_handler.ai_notes.extract_addressed_question", return_value="x?").start()
        self.addCleanup(patch.stopall)

    async def test_a_question_to_me_gets_no_reply_and_no_ai_call(self):
        self.h._process_sentence("Saad Naeem, what is an NP problem?", "Ali")
        self.assertIsNone(self.h._question_answer_task)
        self.h._process_sentence("Saad Naeem is lecture par apna khayal dein", "Ali")   # ambiguous
        self.assertIsNone(self.h._ai_check_task)
        self.judge.assert_not_called()

    async def test_the_attendance_keyword_with_my_name_still_marks_present(self):
        self.h._process_sentence("Attendance, Saad Naeem", "Teacher")
        self.assertIsNotNone(self.h._present_request)
        self.assertIsNone(self.h._question_answer_task)

    async def test_a_bare_roll_call_still_marks_present(self):
        self.h._process_sentence("Saad Naeem", "Teacher")
        self.assertEqual(self.h._present_request["how"], "Roll call")

    async def test_a_question_to_me_is_not_mistaken_for_a_roll_call(self):
        self.h._process_sentence("24K3074", "Teacher")                 # pending roll call (4 s grace)
        self.h._process_sentence("24K3074, what is an NP problem?", "Teacher")
        self.assertIsNone(self.h._present_request)

    async def test_the_question_is_still_logged_for_the_notes(self):
        from unittest.mock import Mock
        self.h.recorder = Mock()
        self.h._process_sentence("Saad Naeem, what is an NP problem?", "Ali")
        self.h.recorder.add_question.assert_called()
