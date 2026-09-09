"""FRIDAY's ears and mouth: microphone capture + STT in, TTS + playback out.

``Ears.listen()`` blocks until you speak and then go quiet, and returns the
transcript.

``Mouth.say()`` queues a line and returns immediately; a background thread
synthesises it with Piper and plays it, so speech for sentence N can start
while sentence N+1 is still being synthesised (and while the model is still
writing it). ``Mouth.wait()`` blocks until the queue has drained and the last
line has finished playing — call it before listening again.

Both load their model once, at construction.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from .config import Config

_INPUT_WAV = "user_input.wav"


class Ears:
    """Microphone capture with silence detection, then faster-whisper."""

    def __init__(self, cfg: Config) -> None:
        from faster_whisper import WhisperModel

        self._cfg = cfg
        self._model = WhisperModel(
            cfg.whisper_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute_type,
            cpu_threads=cfg.whisper_cpu_threads,
        )

    # -- recording ------------------------------------------------------
    def _record(self, path: str, on_level=None, should_stop=None) -> str | None:
        cfg = self._cfg
        audio_q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata, _frames, _time, status):  # noqa: ANN001
            if status:
                print(status, file=sys.stderr)
            audio_q.put(indata.copy())

        print("\n🎙️  listening…")
        stream = sd.InputStream(
            samplerate=cfg.sample_rate,
            channels=cfg.channels,
            callback=callback,
            blocksize=cfg.chunk_size,
        )

        frames: list[np.ndarray] = []
        has_spoken = False
        speech_start = time.monotonic()
        silence_start: float | None = None
        capture_start = time.monotonic()

        with stream:
            while True:
                # A caller (the UI) can pull us out early — e.g. the user
                # typed a message instead of speaking, or muted the mic.
                if should_stop is not None and should_stop():
                    return None
                if time.monotonic() - capture_start > cfg.max_recording_seconds:
                    if has_spoken:
                        print("⏱️  max length reached.")
                        break
                    # Nothing but silence for the whole window — bail so the
                    # loop can re-prompt instead of hanging forever.
                    print("⏱️  heard nothing.")
                    return None
                try:
                    data = audio_q.get(timeout=0.2)
                except queue.Empty:
                    continue

                frames.append(data)
                rms = float(np.sqrt(np.mean(data**2)))
                if on_level is not None:
                    on_level(rms)

                if rms > cfg.silence_threshold:
                    if not has_spoken:
                        has_spoken = True
                        speech_start = time.monotonic()
                        print("🗣️  recording…")
                    silence_start = None
                    continue

                if not has_spoken:
                    continue
                if silence_start is None:
                    silence_start = time.monotonic()
                if time.monotonic() - silence_start > cfg.silence_duration:
                    if time.monotonic() - speech_start > cfg.min_speech_duration:
                        break
                    has_spoken = False
                    silence_start = None

        if not frames:
            return None

        recording = np.concatenate(frames, axis=0)
        clipped = np.clip(recording, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(cfg.channels)
            wf.setsampwidth(2)
            wf.setframerate(cfg.sample_rate)
            wf.writeframes(pcm16.tobytes())
        return path

    # -- transcription -------------------------------------------------
    def listen(self, on_level=None, should_stop=None) -> str | None:
        """Record a phrase and transcribe it.

        ``on_level(rms)`` is called for each audio chunk while recording (for a
        UI meter); ``should_stop()`` is polled ~5x/second and, if it returns
        true, recording aborts and ``listen`` returns ``None``.
        """
        path = self._record(_INPUT_WAV, on_level, should_stop)
        if not path or Path(path).stat().st_size < 1024:
            return None

        started = time.monotonic()
        segments, _info = self._model.transcribe(path, beam_size=5)
        text = "".join(seg.text for seg in segments).strip()
        if not text:
            return None
        print(f"   (heard in {time.monotonic() - started:.1f}s)")
        return text


class Mouth:
    """Piper synthesis + playback, pipelined on a background thread."""

    def __init__(self, cfg: Config) -> None:
        from piper import PiperVoice

        voice_path = cfg.piper_voice_path
        config_path = cfg.piper_config_path
        if not voice_path.is_file():
            raise FileNotFoundError(f"Piper voice not found: {voice_path}")
        if not config_path.is_file():
            raise FileNotFoundError(f"Piper voice config not found: {config_path}")

        self._voice = PiperVoice.load(str(voice_path), config_path=str(config_path))
        self._rate = int(self._voice.config.sample_rate)
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self) -> None:
        while True:
            text = self._queue.get()
            try:
                audio = self._synthesize(text)
                sd.wait()  # let the previous line finish
                if audio is not None:
                    sd.play(audio, samplerate=self._rate)
            except Exception as exc:  # noqa: BLE001 — a TTS hiccup mustn't kill the thread
                print(f"  tts error: {exc}", file=sys.stderr)
            finally:
                self._queue.task_done()

    def _synthesize(self, text: str) -> np.ndarray | None:
        parts = [
            chunk.audio_int16_array for chunk in self._voice.synthesize(text)
        ]
        return np.concatenate(parts) if parts else None

    def say(self, text: str) -> None:
        """Queue a line to be spoken. Returns immediately."""
        text = (text or "").strip()
        if text:
            self._queue.put(text)

    def wait(self) -> None:
        """Block until everything queued has been spoken."""
        self._queue.join()
        sd.wait()

    def stop(self) -> None:
        """Drop anything queued and cut off the current line."""
        try:
            while True:
                self._queue.get_nowait()
                self._queue.task_done()
        except queue.Empty:
            pass
        sd.stop()
