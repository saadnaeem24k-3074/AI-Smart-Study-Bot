"""Local transcription of microphone input and meeting playback through WASAPI."""

import io
import logging
import os
import queue
import re
import sys
import threading
import time
import warnings
import wave
from typing import Callable, Optional

import numpy as np

from core.logger import setup_logger

logger = setup_logger("WhisperASR")

# Harmless noise: soundcard warns about tiny gaps in loopback recording, and faster-whisper
# logs every audio chunk at INFO. Keep real warnings/errors only.
warnings.filterwarnings("ignore", message=".*data discontinuity.*")
logging.getLogger("faster_whisper").setLevel(logging.WARNING)

SAMPLE_RATE = 16000
WINDOW_SECONDS = 8
STEP_SECONDS = 5
MIC_WINDOW_SECONDS = 4
MIC_STEP_SECONDS = 2
MIN_AUDIO_PEAK = 0.008

# Groq-hosted Whisper. Free plan: 20 requests/min and 7,200 audio-seconds/hour, so audio is
# sent in ~20 s batches (22 s windows, small overlap) and requests are spaced >= 3.5 s apart.
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]   # falls back to turbo if large-v3 is refused
GROQ_WINDOW_SECONDS = 22
GROQ_STEP_SECONDS = 20
GROQ_MIN_INTERVAL = 3.5

_ASR_JUNK = re.compile(
    r"\b(?:thank\s+(?:you|u)\s+for\s+watching|thanks?\s+for\s+watching|please subscribe|"
    r"like and subscribe|subscribe to (?:my|the|this) channel|"
    r"see you in the next video)\b",
    re.I,
)


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
    """Transcribe the default microphone and rendered playback locally."""

    _active: Optional["WhisperRecognizer"] = None     # only one may own the audio devices

    def __init__(self, on_transcript: Optional[Callable[[str], None]] = None,
                 model_size: str = "base",
                 on_speech: Optional[Callable[[str, str], None]] = None):
        self.on_transcript = on_transcript
        self.on_speech = on_speech
        self.model_size = model_size
        self.audio_queue: queue.Queue = queue.Queue(maxsize=128)
        self.running = False
        self.model = None
        self._thread: Optional[threading.Thread] = None
        self._transcriber: Optional[threading.Thread] = None
        self._capture_threads = []
        self._capture_finished = threading.Event()
        self._capture_finished.set()
        self._last_text = ""
        self._last_text_by_source = {}
        self._reported_overflow = False
        self._cuda_dll_directory: Optional[object] = None
        backend = os.environ.get("WHISPER_BACKEND", "auto").strip().lower()    # auto | groq | local
        self._groq_key = "" if backend == "local" else self._find_groq_key()
        self.use_groq = bool(self._groq_key)
        if backend == "groq" and not self.use_groq:
            logger.warning("WHISPER_BACKEND=groq but no Groq API key was found; using local Whisper.")
        self._groq_model = os.environ.get("GROQ_WHISPER_MODEL", "").strip() or GROQ_MODELS[0]
        self._groq_last = 0.0

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

    @staticmethod
    def _default_microphone(soundcard):
        microphone = soundcard.default_microphone()
        if microphone is None:
            raise RuntimeError("No default Windows microphone is available.")
        return microphone, str(microphone.name)

    def start(self):
        if self.running:
            return
        previous = WhisperRecognizer._active
        if previous is not None and previous is not self:
            # back-to-back classes: make sure the last class released the audio devices
            previous.stop()
        WhisperRecognizer._active = self
        self.running = True
        self._capture_finished.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Local microphone and playback transcription starting (Whisper base model).")

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
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
            if self.use_groq:
                logger.info(f"Transcribing with Groq Whisper ({self._groq_model}); local model is a fallback only.")
            else:
                self._load_local()
            sources = []
            try:
                microphone, microphone_name = self._default_microphone(soundcard)
                sources.append(("microphone", microphone, microphone_name))
            except Exception as e:
                logger.error(f"Could not access the default microphone: {e}")
            try:
                loopback, speaker_name = self._loopback_microphone(soundcard)
                sources.append(("playback", loopback, speaker_name))
            except Exception as e:
                logger.error(f"Could not access default-speaker loopback: {e}")
            if not sources:
                raise RuntimeError("No microphone or playback source could be opened.")

            self._transcriber = threading.Thread(target=self._transcribe_queue, daemon=True)
            self._transcriber.start()
            capture_threads = [
                threading.Thread(
                    target=self._capture_source,
                    args=(source, microphone, name),
                    daemon=True,
                )
                for source, microphone, name in sources
            ]
            self._capture_threads = capture_threads
            for thread in capture_threads:
                thread.start()
            logger.info(
                "Capturing enabled local audio sources: "
                + ", ".join(f"{source} '{name}'" for source, _, name in sources)
            )
            while self.running and any(thread.is_alive() for thread in capture_threads):
                time.sleep(0.1)
        except ImportError as e:
            logger.error(
                "Local speech transcription is unavailable. Install the configured "
                "audio/ASR dependencies with: pip install soundcard faster-whisper "
                f"({e})"
            )
        except Exception as e:
            logger.error(f"Could not capture or transcribe local audio: {e}")
            logger.info(
                "Check the selected Windows microphone and playback devices, their privacy "
                "permissions, and restart the class."
            )
        finally:
            self.running = False
            for thread in self._capture_threads:
                if thread.is_alive():
                    thread.join(timeout=5)
                    if thread.is_alive():
                        logger.warning("An audio capture worker is still stopping.")
            self._capture_finished.set()
            if self._transcriber and self._transcriber.is_alive():
                self._transcriber.join(timeout=15)
                if self._transcriber.is_alive():
                    logger.warning("Whisper worker is still finishing its current audio chunk.")

    def _capture_source(self, source, microphone, name):
        try:
            with microphone.recorder(samplerate=SAMPLE_RATE, blocksize=4096) as recorder:
                while self.running:
                    audio = recorder.record(numframes=4096)
                    self._queue_audio(audio, source)
        except Exception as e:
            if source == "microphone" and self.running:
                logger.warning(
                    f"SoundCard could not capture microphone audio from '{name}' "
                    f"({e!r}); trying PyAudio."
                )
                try:
                    self._capture_pyaudio_microphone(name)
                except Exception as fallback_error:
                    logger.error(
                        f"Could not capture microphone audio from '{name}' with "
                        f"SoundCard or PyAudio: {fallback_error!r}",
                        exc_info=True,
                    )
            elif self.running:
                logger.error(
                    f"Could not capture {source} audio from '{name}': {e!r}",
                    exc_info=True,
                )

    def _capture_pyaudio_microphone(self, name):
        import pyaudio

        audio_interface = pyaudio.PyAudio()
        stream = None
        try:
            device = audio_interface.get_default_input_device_info()
            device_index = int(device["index"])
            device_name = str(device.get("name") or name)
            default_rate = int(device["defaultSampleRate"])
            channels = 1
            last_error = None
            sample_rate = SAMPLE_RATE
            for sample_rate in dict.fromkeys((SAMPLE_RATE, default_rate)):
                try:
                    stream = audio_interface.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=sample_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=4096,
                    )
                    break
                except Exception as e:
                    last_error = e
            if stream is None:
                raise RuntimeError(
                    f"Could not open default input device '{device_name}': {last_error!r}"
                )

            logger.info(
                f"Capturing microphone '{device_name}' through PyAudio at {sample_rate} Hz."
            )
            while self.running:
                raw_audio = stream.read(4096, exception_on_overflow=False)
                audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                audio /= 32768.0
                if sample_rate != SAMPLE_RATE and audio.size:
                    output_size = max(1, round(audio.size * SAMPLE_RATE / sample_rate))
                    positions = np.arange(output_size, dtype=np.float32) * (
                        sample_rate / SAMPLE_RATE
                    )
                    audio = np.interp(
                        positions,
                        np.arange(audio.size, dtype=np.float32),
                        audio,
                    ).astype(np.float32)
                self._queue_audio(audio, "microphone")
        finally:
            try:
                if stream is not None:
                    try:
                        stream.stop_stream()
                    finally:
                        stream.close()
            finally:
                audio_interface.terminate()

    @staticmethod
    def _find_groq_key() -> str:
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if key:
            return key
        try:                                   # key saved in Dashboard -> Settings -> AI provider
            from core import config_store
            return config_store.ai_key(config_store.load_raw(), "groq")
        except Exception:
            return ""

    def _load_local(self):
        from faster_whisper import WhisperModel
        try:
            logger.info(f"Loading faster-whisper '{self.model_size}' model on the NVIDIA GPU (first run downloads it).")
            self.model = WhisperModel(self.model_size, device="cuda", compute_type="float32")
        except (OSError, RuntimeError) as e:
            logger.warning(f"Whisper GPU initialization failed ({e}); falling back to CPU.")
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def _ensure_local(self) -> bool:
        if self.model is not None:
            return True
        try:
            self._load_local()
            return True
        except Exception as e:
            logger.error(f"Local Whisper fallback is unavailable: {e}")
            return False

    def _next_groq_model(self) -> bool:
        i = GROQ_MODELS.index(self._groq_model) if self._groq_model in GROQ_MODELS else -1
        if i + 1 < len(GROQ_MODELS):
            logger.warning(f"Groq refused '{self._groq_model}'; switching to '{GROQ_MODELS[i + 1]}'.")
            self._groq_model = GROQ_MODELS[i + 1]
            return True
        return False

    @staticmethod
    def _parse_groq(body: dict):
        parts = []
        for seg in body.get("segments") or [{"text": body.get("text", "")}]:
            text = str(seg.get("text", "")).strip()
            if (not text or seg.get("no_speech_prob", 0.0) > 0.6 or seg.get("avg_logprob", 0.0) < -1.0
                    or seg.get("compression_ratio", 0.0) > 2.4 or _ASR_JUNK.search(text)):
                continue
            parts.append(text)
        return " ".join(parts), body.get("language") or "unknown"

    def _transcribe_groq(self, audio: np.ndarray):
        """(text, language) on success - text may be empty for silence - or None if Groq failed."""
        import requests
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        wav = buf.getvalue()
        extra = {"language": os.environ["GROQ_WHISPER_LANGUAGE"]} if os.environ.get("GROQ_WHISPER_LANGUAGE") else {}
        for _ in range(3):
            wait = GROQ_MIN_INTERVAL - (time.monotonic() - self._groq_last)
            if wait > 0:
                time.sleep(wait)
            self._groq_last = time.monotonic()
            try:
                r = requests.post(
                    GROQ_URL, headers={"Authorization": f"Bearer {self._groq_key}"},
                    files={"file": ("audio.wav", wav, "audio/wav")},
                    data={"model": self._groq_model, "response_format": "verbose_json", "temperature": "0", **extra},
                    timeout=60)
            except requests.RequestException as e:
                logger.warning(f"Groq request failed: {e}")
                continue
            if r.status_code == 200:
                return self._parse_groq(r.json())
            if r.status_code == 429:
                try:
                    delay = float(r.headers.get("retry-after", 10))
                except ValueError:
                    delay = 10.0
                logger.warning(f"Groq rate limit reached; waiting {min(delay, 30):.0f}s.")
                time.sleep(min(delay, 30))
                continue
            if r.status_code == 401:
                logger.error("Groq rejected the API key; using the local model instead.")
                self.use_groq = False
                return None
            if r.status_code in (400, 404) and "model" in r.text.lower() and self._next_groq_model():
                continue
            logger.warning(f"Groq transcription failed ({r.status_code}): {r.text[:200]}")
            return None
        return None

    def _queue_audio(self, audio, source="playback"):
        if audio is None:
            return
        block = np.asarray(audio, dtype=np.float32)
        if block.ndim == 2:
            block = block.mean(axis=1)
        try:
            self.audio_queue.put_nowait((source, block))
        except queue.Full:
            if not self._reported_overflow:
                logger.warning("Whisper audio queue is full; dropping old audio while transcription catches up.")
                self._reported_overflow = True
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait((source, block))
            except (queue.Empty, queue.Full):
                pass

    def _transcribe_queue(self):
        if self.use_groq:        # bigger, rarer batches keep us under Groq's 20 requests/min
            mic_w = pb_w = GROQ_WINDOW_SECONDS
            mic_s = pb_s = GROQ_STEP_SECONDS
        else:
            mic_w, mic_s, pb_w, pb_s = MIC_WINDOW_SECONDS, MIC_STEP_SECONDS, WINDOW_SECONDS, STEP_SECONDS
        windows = {"microphone": SAMPLE_RATE * mic_w, "playback": SAMPLE_RATE * pb_w}
        steps = {"microphone": SAMPLE_RATE * mic_s, "playback": SAMPLE_RATE * pb_s}
        buffered = {source: np.empty((0,), dtype=np.float32) for source in windows}
        while self.running or not self._capture_finished.is_set() or not self.audio_queue.empty():
            try:
                source, block = self.audio_queue.get(timeout=0.25)
                if source not in buffered:
                    logger.warning(f"Ignoring audio from unknown source '{source}'.")
                    continue
                buffered[source] = np.concatenate(
                    (buffered[source], block.astype(np.float32, copy=False))
                )
            except queue.Empty:
                if not self.running and self._capture_finished.is_set():
                    break
                continue

            while self.running and buffered[source].size >= windows[source]:
                audio = buffered[source][:windows[source]]
                buffered[source] = buffered[source][steps[source]:]
                if float(np.max(np.abs(audio))) < MIN_AUDIO_PEAK:
                    self._last_text_by_source[source] = ""
                    continue
                self._transcribe(audio, source)

        for source, audio in buffered.items():
            if audio.size >= SAMPLE_RATE * 2 and float(np.max(np.abs(audio))) >= MIN_AUDIO_PEAK:
                self._transcribe(audio, source)

    def _transcribe(self, audio: np.ndarray, source="playback"):
        if self.use_groq:
            result = self._transcribe_groq(audio)
            if result is not None:
                self._emit(result[0], result[1], source)
                return
            if not self._ensure_local():
                return
            logger.warning("Groq was unavailable for this chunk; using the local model.")
        try:
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.6,
                    "min_speech_duration_ms": 250,
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 250,
                },
                no_speech_threshold=0.6,
                log_prob_threshold=-0.9,
                compression_ratio_threshold=2.3,
                condition_on_previous_text=False,
                language=os.environ.get("WHISPER_LANGUAGE", "").strip() or None,
            )
            accepted = []
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                if getattr(segment, "no_speech_prob", 0.0) > 0.6:
                    continue
                if getattr(segment, "avg_logprob", 0.0) < -0.9:
                    continue
                if getattr(segment, "compression_ratio", 0.0) > 2.3:
                    continue
                if _ASR_JUNK.search(text):
                    logger.info("Ignoring a common end-card / background-audio transcription artifact.")
                    continue
                accepted.append(text)
            text = " ".join(accepted)
        except Exception as e:
            logger.error(f"Whisper audio chunk failed: {e}")
            return
        self._emit(text, getattr(info, "language", None) or "unknown", source)

    def _emit(self, text: str, language: str, source: str):
        previous_text = self._last_text_by_source.get(source, "")
        text = _strip_overlap(previous_text, text)
        if not text:
            return
        self._last_text_by_source[source] = " ".join((previous_text + " " + text).split())[-500:]
        self._last_text = self._last_text_by_source[source]
        logger.info(f"[Whisper:{source}:{language}] {text}")
        if self.on_transcript:
            self.on_transcript(text)
        if self.on_speech:
            self.on_speech(text, source)
