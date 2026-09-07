"""FRIDAY's ears and mouth: microphone capture + STT in, TTS + playback out.

``Ears.listen()`` blocks until you speak and then go quiet, and returns the
transcript. ``Mouth.say()`` synthesises a line with Piper and plays it. Both
load their model once, at construction.
"""

from __future__ import annotations

import queue
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from .config import Config

_INPUT_WAV = "user_input.wav"
_OUTPUT_WAV = "friday_response.wav"


class Ears:
    """Microphone capture with silence detection, then faster-whisper."""

    def __init__(self, cfg: Config) -> None:
        from faster_whisper import WhisperModel

        self._cfg = cfg
        self._model = WhisperModel(
            cfg.whisper_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute_type,
        )

    # -- recording ------------------------------------------------------
    def _record(self, path: str) -> str | None:
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
    def listen(self) -> str | None:
        path = self._record(_INPUT_WAV)
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
    """Piper synthesis + playback."""

    def __init__(self, cfg: Config) -> None:
        from piper import PiperVoice

        voice_path = cfg.piper_voice_path
        config_path = cfg.piper_config_path
        if not voice_path.is_file():
            raise FileNotFoundError(f"Piper voice not found: {voice_path}")
        if not config_path.is_file():
            raise FileNotFoundError(f"Piper voice config not found: {config_path}")

        self._voice = PiperVoice.load(str(voice_path), config_path=str(config_path))

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        with wave.open(_OUTPUT_WAV, "wb") as wf:
            self._voice.synthesize_wav(text, wf)

        with wave.open(_OUTPUT_WAV, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            sd.play(audio, samplerate=wf.getframerate())
            sd.wait()
