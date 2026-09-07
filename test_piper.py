"""TTS smoke test: synthesize one line with Piper, no mic or brain involved.

    python test_piper.py
"""

import wave

from piper import PiperVoice

VOICE = "en_GB-jenny_dioco-medium.onnx"  # the voice friday.py uses

print(f"Loading {VOICE} ...")
voice = PiperVoice.load(VOICE, config_path=VOICE + ".json")

text = "Hello, this is Friday speaking for the first time."
print(f"Synthesizing: {text}")
with wave.open("test_voice.wav", "wb") as wav_file:
    voice.synthesize_wav(text, wav_file)

print("Done. Saved to test_voice.wav")
