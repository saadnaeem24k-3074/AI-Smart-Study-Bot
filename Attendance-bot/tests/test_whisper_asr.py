import unittest

import numpy as np

from detection.whisper_asr import WhisperRecognizer, _strip_overlap


class WhisperOverlapTests(unittest.TestCase):
    def test_removes_repeated_words_from_overlapping_chunks(self):
        self.assertEqual(
            _strip_overlap(
                "The derivative is the rate of change",
                "rate of change of a function.",
            ),
            "of a function.",
        )

    def test_preserves_non_overlapping_chunk_text(self):
        self.assertEqual(
            _strip_overlap("We discussed the derivative.", "Now consider the integral."),
            "Now consider the integral.",
        )

    def test_keeps_single_common_word_at_chunk_boundary(self):
        self.assertEqual(_strip_overlap("It is", "is a new topic."), "is a new topic.")

    def test_emits_transcribed_text_from_model(self):
        class Segment:
            text = "The derivative is the rate of change."

        class Language:
            language = "en"

        class FakeModel:
            def transcribe(self, audio, **options):
                self.audio = audio
                self.options = options
                return iter([Segment()]), Language()

        captured = []
        recognizer = WhisperRecognizer(on_transcript=captured.append)
        recognizer.model = FakeModel()

        recognizer._transcribe(np.ones(16000, dtype=np.float32))

        self.assertEqual(captured, ["The derivative is the rate of change."])
        self.assertTrue(recognizer.model.options["vad_filter"])
        self.assertFalse(recognizer.model.options["condition_on_previous_text"])

    def test_transcribes_remaining_audio_when_stopped(self):
        class Segment:
            text = "The final part of the lecture."

        class Language:
            language = "en"

        class FakeModel:
            def transcribe(self, audio, **options):
                return iter([Segment()]), Language()

        captured = []
        recognizer = WhisperRecognizer(on_transcript=captured.append)
        recognizer.model = FakeModel()
        recognizer._queue_audio(np.ones(4 * 16000, dtype=np.float32))
        recognizer.running = False

        recognizer._transcribe_queue()

        self.assertEqual(captured, ["The final part of the lecture."])


class WasapiDeviceTests(unittest.TestCase):
    def test_selects_loopback_for_default_speaker(self):
        class Speaker:
            name = "Default speakers"

        class LoopbackMicrophone:
            pass

        class FakeSoundCard:
            @staticmethod
            def default_speaker():
                return Speaker()

            @staticmethod
            def get_microphone(id, include_loopback=False):
                assert id == "Default speakers"
                assert include_loopback is True
                return LoopbackMicrophone()

        microphone, name = WhisperRecognizer._loopback_microphone(FakeSoundCard)

        self.assertIsInstance(microphone, LoopbackMicrophone)
        self.assertEqual(name, "Default speakers")

    def test_reports_missing_playback_device(self):
        class FakeSoundCard:
            @staticmethod
            def default_speaker():
                return None

        with self.assertRaisesRegex(RuntimeError, "default Windows playback"):
            WhisperRecognizer._loopback_microphone(FakeSoundCard)


if __name__ == "__main__":
    unittest.main()
