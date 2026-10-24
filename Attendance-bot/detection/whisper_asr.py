"""Local transcription of meeting playback through Windows WASAPI loopback."""

import os
import queue
import re
import sys
import threading
from typing import Callable, Optional

import numpy as np

from core.logger import setup_logger

logger = setup_logger("WhisperASR")

SAMPLE_RATE = 16000
WINDOW_SECONDS = 12
STEP_SECONDS = 8


def _strip_overlap(previous: str, current: str, max_words: int = 24) -> str:
    """Remove exact repeated words from adjacent, overlapping audio chunks."""
    previous_words = list(re.finditer(r"\w+", previous.casefold()))
    current_words = list(re.finditer(r"\w+", current.casefold()))
    limit = min(max_words, len(previous_words), len(current_words))
    overlap = 0
    for size in range(2, limit + 1):
        left = [match.group() for match in previous_words[-size:]]
        right = [match.group() for match in current_words[:size]]
        if left == right:
            overlap = size
    if not overlap:
        return current.strip()
    return current[current_words[overlap - 1].end():].lstrip(" \t,.;:!?-")


class WhisperRecognizer:
    """Capture rendered meeting audio and emit local, auto-language transcripts."""

    def __init__(self, on_transcript: Optional[Callable[[str], None]] = None,
                 model_size: str = "base"):
        self.on_transcript = on_transcript
        self.model_size = model_size
        self.audio_queue: queue.Queue = queue.Queue(maxsize=128)
        self.running = False
        self.model = None
        self._thread: Optional[threading.Thread] = None
        self._transcriber: Optional[threading.Thread] = None
        self._capture_finished = threading.Event()
        self._capture_finished.set()
        self._last_text = ""
        self._reported_overflow = False
        self._cuda_dll_directory: Optional[object] = None

    @staticmethod
    def _loopback_microphone(soundcard):
        speaker = soundcard.default_speaker()
        if speaker is None:
            raise RuntimeError("No default Windows playback device is available.")
        microphone = soundcard.get_microphone(
            id=str(speaker.name),
            include_loopback=True,
        )
        if microphone is None:
            raise RuntimeError(f"No WASAPI loopback endpoint found for '{speaker.name}'.")
        return microphone, str(speaker.name)

    def start(self):
        if self.running:
            return
        self.running = True
        self._capture_finished.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Local audio transcription starting (WASAPI loopback, Whisper base model).")

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                logger.warning("Whisper worker is still finishing its current audio chunk.")
        logger.info("Local audio transcription stopped.")

    def _capture_loop(self):
        try:
            if sys.platform == "win32":
                dll_directory = os.path.dirname(sys.executable)
                if dll_directory not in os.environ.get("PATH", "").split(os.pathsep):
                    os.environ["PATH"] = (
                        dll_directory + os.pathsep + os.environ.get("PATH", "")
                    )
                self._cuda_dll_directory = os.add_dll_directory(dll_directory)
            import soundcard
            from faster_whisper import WhisperModel

            try:
                logger.info(
                    f"Loading faster-whisper '{self.model_size}' model on the NVIDIA GPU "
                    "(first run downloads it)."
                )
                self.model = WhisperModel(
                    self.model_size,
                    device="cuda",
                    compute_type="float32",
                )
            except (OSError, RuntimeError) as e:
                logger.warning(f"Whisper GPU initialization failed ({e}); falling back to CPU.")
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                )
            microphone, speaker_name = self._loopback_microphone(soundcard)
            logger.info(
                f"Capturing shared meeting playback from '{speaker_name}' "
                f"at {SAMPLE_RATE} Hz; detected language is automatic."
            )
            with microphone.recorder(samplerate=SAMPLE_RATE, blocksize=4096) as recorder:
                self._transcriber = threading.Thread(target=self._transcribe_queue, daemon=True)
                self._transcriber.start()
                while self.running:
                    audio = recorder.record(numframes=4096)
                    self._queue_audio(audio)
        except ImportError as e:
            logger.error(
                "Local speech transcription is unavailable. Install the configured "
                "audio/ASR dependencies with: pip install soundcard faster-whisper "
                f"({e})"
            )
        except Exception as e:
            logger.error(f"Could not capture or transcribe meeting playback: {e}")
            logger.info(
                "Check that the meeting is audible on the selected Windows output device, "
                "then restart the class. WASAPI loopback does not require a virtual cable."
            )
        finally:
            self.running = False
            self._capture_finished.set()
            if self._transcriber and self._transcriber.is_alive():
                self._transcriber.join(timeout=15)
                if self._transcriber.is_alive():
                    logger.warning("Whisper worker is still finishing its current audio chunk.")

    def _queue_audio(self, audio):
        if audio is None:
            return
        block = np.asarray(audio, dtype=np.float32)
        if block.ndim == 2:
            block = block.mean(axis=1)
        try:
            self.audio_queue.put_nowait(block)
        except queue.Full:
            if not self._reported_overflow:
                logger.warning("Whisper audio queue is full; dropping old audio while transcription catches up.")
                self._reported_overflow = True
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(block)
            except (queue.Empty, queue.Full):
                pass

    def _transcribe_queue(self):
        window = SAMPLE_RATE * WINDOW_SECONDS
        step = SAMPLE_RATE * STEP_SECONDS
        buffered = np.empty((0,), dtype=np.float32)
        while self.running or not self._capture_finished.is_set() or not self.audio_queue.empty():
            try:
                block = self.audio_queue.get(timeout=0.25)
                buffered = np.concatenate((buffered, block.astype(np.float32, copy=False)))
            except queue.Empty:
                if not self.running and self._capture_finished.is_set():
                    break
                continue

            while self.running and buffered.size >= window:
                audio = buffered[:window]
                buffered = buffered[step:]
                if float(np.max(np.abs(audio))) < 0.008:
                    self._last_text = ""
                    continue
                self._transcribe(audio)

        if buffered.size >= SAMPLE_RATE * 2 and float(np.max(np.abs(buffered))) >= 0.008:
            self._transcribe(buffered)

    def _transcribe(self, audio: np.ndarray):
        try:
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        except Exception as e:
            logger.error(f"Whisper audio chunk failed: {e}")
            return
        text = _strip_overlap(self._last_text, text)
        if not text:
            return
        self._last_text = " ".join((self._last_text + " " + text).split())[-500:]
        language = getattr(info, "language", None) or "unknown"
        logger.info(f"[Whisper:{language}] {text}")
        if self.on_transcript:
            self.on_transcript(text)
