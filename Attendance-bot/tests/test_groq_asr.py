import os, sys, unittest
from unittest import mock
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection import whisper_asr as w


class R:
    def __init__(self, code, body=None, text="", headers=None):
        self.status_code, self._b, self.text, self.headers = code, body or {}, text, headers or {}
    def json(self):
        return self._b


class GroqAsrTests(unittest.TestCase):
    def make(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k", "WHISPER_BACKEND": "groq"}):
            return w.WhisperRecognizer()

    def run_chunk(self, rec, responses):
        with mock.patch("requests.post", side_effect=responses), mock.patch.object(w.time, "sleep"):
            return rec._transcribe_groq(np.zeros(16000, dtype=np.float32))

    def test_parses_and_filters_segments(self):
        body = {"language": "en", "segments": [{"text": " Hello class", "no_speech_prob": 0.1, "avg_logprob": -0.2},
                                                {"text": "noise", "no_speech_prob": 0.9, "avg_logprob": -0.2}]}
        self.assertEqual(self.run_chunk(self.make(), [R(200, body)]), ("Hello class", "en"))

    def test_falls_back_to_turbo_when_model_refused(self):
        rec = self.make()
        out = self.run_chunk(rec, [R(404, text="model not found"), R(200, {"text": "ok"})])
        self.assertEqual(out[0], "ok")
        self.assertEqual(rec._groq_model, "whisper-large-v3-turbo")

    def test_bad_key_switches_to_local(self):
        rec = self.make()
        self.assertIsNone(self.run_chunk(rec, [R(401)]))
        self.assertFalse(rec.use_groq)

    def test_rate_limit_is_retried(self):
        out = self.run_chunk(self.make(), [R(429, headers={"retry-after": "1"}), R(200, {"text": "again"})])
        self.assertEqual(out[0], "again")


if __name__ == "__main__":
    unittest.main()
