import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
        self.assertEqual(recognizer.model.options["vad_parameters"]["threshold"], 0.6)
        self.assertEqual(recognizer.model.options["no_speech_threshold"], 0.6)
        self.assertFalse(recognizer.model.options["condition_on_previous_text"])

    def test_emits_source_for_microphone_speech(self):
        class Segment:
            text = "What is the derivative?"

        class Language:
            language = "en"

        class FakeModel:
            def transcribe(self, audio, **options):
                return iter([Segment()]), Language()

        captured = []
        recognizer = WhisperRecognizer(on_speech=lambda text, source: captured.append((text, source)))
        recognizer.model = FakeModel()

        recognizer._transcribe(np.ones(16000, dtype=np.float32), source="microphone")

        self.assertEqual(captured, [("What is the derivative?", "microphone")])

    def test_drops_low_confidence_and_common_video_outro_hallucinations(self):
        class Segment:
            def __init__(self, text, no_speech_prob=0.0, avg_logprob=-0.1, compression_ratio=1.0):
                self.text = text
                self.no_speech_prob = no_speech_prob
                self.avg_logprob = avg_logprob
                self.compression_ratio = compression_ratio

        class Language:
            language = "en"

        class FakeModel:
            def transcribe(self, audio, **options):
                return iter([
                    Segment("The first concept is valid."),
                    Segment("Background hiss sounds like words.", no_speech_prob=0.8),
                    Segment("Thank u for watching dis video."),
                    Segment("Repeated text.", compression_ratio=3.0),
                ]), Language()

        captured = []
        recognizer = WhisperRecognizer(on_transcript=captured.append)
        recognizer.model = FakeModel()

        recognizer._transcribe(np.ones(16000, dtype=np.float32))

        self.assertEqual(captured, ["The first concept is valid."])

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
    def test_selects_default_microphone(self):
        class Microphone:
            name = "Headset microphone"

        class FakeSoundCard:
            @staticmethod
            def default_microphone():
                return Microphone()

        microphone, name = WhisperRecognizer._default_microphone(FakeSoundCard)

        self.assertEqual(name, "Headset microphone")
        self.assertIsInstance(microphone, Microphone)

    def test_keeps_microphone_and_playback_audio_buffers_separate(self):
        recognizer = WhisperRecognizer()
        recognizer._queue_audio(np.ones(4 * 16000, dtype=np.float32), "microphone")
        recognizer._queue_audio(np.ones(8 * 16000, dtype=np.float32), "playback")
        sources = []
        recognizer._transcribe = lambda audio, source: sources.append(source)
        recognizer.running = False

        recognizer._transcribe_queue()

        self.assertCountEqual(sources, ["microphone", "playback"])

    def test_microphone_capture_falls_back_to_pyaudio(self):
        class BrokenRecorder:
            def __enter__(self):
                raise RuntimeError()

            def __exit__(self, *_args):
                return False

        class Microphone:
            @staticmethod
            def recorder(**_kwargs):
                return BrokenRecorder()

        recognizer = WhisperRecognizer()
        recognizer.running = True
        with patch.object(recognizer, "_capture_pyaudio_microphone") as fallback:
            recognizer._capture_source("microphone", Microphone(), "Headset microphone")

        fallback.assert_called_once_with("Headset microphone")

    def test_pyaudio_microphone_resamples_default_device_audio(self):
        captured = []
        recognizer = WhisperRecognizer()

        class FakeStream:
            def read(self, _frames, exception_on_overflow=False):
                self.exception_on_overflow = exception_on_overflow
                recognizer.running = False
                return np.ones(4096, dtype=np.int16).tobytes()

            def stop_stream(self):
                pass

            def close(self):
                pass

        class FakeAudioInterface:
            def get_default_input_device_info(self):
                return {"index": 3, "name": "USB mic", "defaultSampleRate": 48000}

            def open(self, **options):
                if options["rate"] == 16000:
                    raise ValueError("16 kHz is unsupported")
                self.open_options = options
                return FakeStream()

            def terminate(self):
                pass

        audio_interface = FakeAudioInterface()
        fake_pyaudio = SimpleNamespace(
            PyAudio=lambda: audio_interface,
            paInt16=8,
        )
        recognizer.running = True
        recognizer._queue_audio = lambda audio, source: captured.append((audio, source))
        with patch.dict("sys.modules", {"pyaudio": fake_pyaudio}):
            recognizer._capture_pyaudio_microphone("Default mic")

        self.assertEqual(audio_interface.open_options["rate"], 48000)
        self.assertEqual(captured[0][1], "microphone")
        self.assertEqual(len(captured[0][0]), round(4096 * 16000 / 48000))

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
