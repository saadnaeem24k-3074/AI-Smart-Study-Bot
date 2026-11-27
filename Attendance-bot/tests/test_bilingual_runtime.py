"""Regressions from a real class log: self-answer loop, duplicate answers, Urdu/Hindi misses."""
import asyncio
import unittest
from collections import deque
from unittest.mock import AsyncMock, patch

import numpy as np

from detection import whisper_asr
from detection.attendance_detector import AttendanceDetector
from platforms.meet_handler import MeetHandler, _parse_chat_messages
from utils import ai_notes

CHAT = """5:18 pm
walaikum assalam. my name is 24k 3074, nice to meet you.
hover over a message to pin it
keep
keep
pin message
a
A vertex is a point where edges meet in a graph. What is why how?
keep
Pin message
Clasher Gamer!
5:23 PM
why do we need to study algorithams?
5:23 PM
We study algorithms to solve complex problems efficiently.
keep
Pin message
Clasher Gamer!
5:24 PM
alright 24K-3033 whats the difference between P and NP problem
5:24 PM
P problems are solved quickly by computers.
keep
Pin message
Clasher Gamer!
5:30 PM
24K3074 bataiye NP hard kya hota hai"""


def make_handler():
    return MeetHandler(
        {"subject": "Algorithms"},
        {"student": {"name": "Saad Naeem", "roll_no": "24K-3074", "urdu_names": []},
         "global_settings": {}, "features": {},
         "ai": {"provider": "gemini", "keys": {"gemini": "test-key"}}},
    )


class ChatParsingTests(unittest.TestCase):
    def test_only_other_peoples_messages_are_returned(self):
        messages = _parse_chat_messages(CHAT)
        self.assertEqual(len(messages), 3)
        self.assertTrue(all("p problems are solved" not in m and "we study" not in m
                            and "a vertex" not in m and "walaikum" not in m for m in messages))

    def test_a_message_for_another_roll_number_is_not_mine(self):
        handler = make_handler()
        self.assertFalse(handler._me_called("alright 24k-3033 whats the difference between p and np problem"))
        self.assertTrue(handler._me_called("24k3074 bataiye np hard kya hota hai"))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = make_handler()
        self.handler.captions = deque(["Lecture."], maxlen=50)

    async def _run(self, lines):
        with (
            patch("platforms.meet_handler.ai_notes.api_key", return_value="k"),
            patch("platforms.meet_handler.ai_notes.answer_question", return_value="ok") as answer,
            patch("platforms.meet_handler.ai_notes.extract_addressed_question", return_value=""),
            patch.object(self.handler, "send_chat", new_callable=AsyncMock, return_value=True),
        ):
            for line in lines:
                self.handler._process_sentence(line)
                if self.handler._question_answer_task:
                    await self.handler._question_answer_task
        return answer

    async def test_same_question_heard_via_mic_playback_and_captions_is_answered_once(self):
        answer = await self._run([
            "24K3074 NP hard problem का मतलब क्या है",       # meeting audio (Hindi script)
            "24K3074 NP Heart Problem का मतलब क्या है?",      # microphone
            "24K 3074 NP hard problem ka matlab kya hai",     # captions
        ])
        self.assertEqual(answer.call_count, 1)

    async def test_imperative_question_is_answered_as_said_not_with_an_old_question(self):
        answer = await self._run([
            "why do we need algorithms?",
            "24K3074 मुझे deterministic और non-deterministic algorithm बताओ",
        ])
        self.assertIn("deterministic", answer.call_args.args[2])

    async def test_garbled_roll_number_still_counts_as_my_name(self):
        answer = await self._run(["24K 30.74 MP Heart Program का मतलब क्या है?"])
        self.assertEqual(answer.call_count, 1)

    async def test_my_own_sent_answers_are_never_read_back_as_questions(self):
        self.handler._sent_chat_norms.add("what is slope 24k3074 how are you")
        with patch.object(self.handler, "_queue_live_answer") as queue_answer:
            self.handler._check_for_addressed_chat_questions(["what is slope 24k3074 how are you"])
        queue_answer.assert_not_called()


class WhisperTests(unittest.TestCase):
    def test_segmenter_cuts_at_pauses_and_ignores_noise(self):
        seg = whisper_asr.UtteranceSegmenter()
        rate = whisper_asr.SAMPLE_RATE
        rng = np.random.default_rng(0)
        block = lambda amp, n=4096: (rng.standard_normal(n) * amp).astype(np.float32)
        out = []
        for _ in range(8):                                  # ~2s of room noise
            out += seg.feed(block(0.002))
        for _ in range(12):                                 # ~3s of speech
            out += seg.feed(block(0.2))
        for _ in range(6):                                  # pause -> utterance ends
            out += seg.feed(block(0.002))
        self.assertEqual(len(out), 1)
        self.assertGreater(out[0].size, rate * 3)
        for _ in range(2):                                  # a click is too short to be speech
            out += seg.feed(block(0.2))
        for _ in range(6):
            out += seg.feed(block(0.002))
        self.assertEqual(len(out), 1)

    def test_hallucinations_and_foreign_script_are_dropped(self):
        rec = whisper_asr.WhisperRecognizer(on_speech=lambda t, s: heard.append(t),
                                            prompt_hint="24K3074, Saad Naeem")
        heard = []
        rec._emit("Thank you.", "English", "microphone")
        rec._emit(". . . .", "English", "playback")
        rec._emit("はい", "Japanese", "playback")
        rec._emit("24K3074 Saad Naeem", "English", "microphone")        # echo of the hint
        rec._emit("24K3074 मुझे NP hard बताओ", "Hindi", "microphone")
        self.assertEqual(heard, ["24K3074 मुझे NP hard बताओ"])


class FastLiveCallTests(unittest.TestCase):
    def test_falls_back_to_another_provider_when_the_first_is_overloaded(self):
        cfg = {"ai": {"provider": "gemini", "keys": {"gemini": "g", "groq": "q"}}}
        seen = []

        def fake_call(config, *args, **kwargs):
            seen.append((config["ai"]["provider"], kwargs.get("timeout")))
            return None if config["ai"]["provider"] == "gemini" else '{"answer": "ok"}'

        with patch("utils.ai_notes._call", side_effect=fake_call):
            out = ai_notes._call_live(cfg, "q", 100, system="s")
        self.assertEqual(out, '{"answer": "ok"}')
        self.assertEqual([p for p, _ in seen], ["gemini", "groq"])
        self.assertTrue(all(t == 12 for _, t in seen))

    def test_live_prompt_only_carries_recent_lecture(self):
        cfg = {"features": {}, "ai": {"provider": "gemini", "keys": {"gemini": "k"}}}
        with patch("utils.ai_notes._call", return_value='{"answer": "ok"}') as call:
            ai_notes.answer_question(cfg, "OLD " * 5000 + "RECENT", "what is slope?", None, True)
        prompt = call.call_args.args[1]
        self.assertIn("RECENT", prompt)
        self.assertLess(len(prompt), 6000)


if __name__ == "__main__":
    unittest.main()
