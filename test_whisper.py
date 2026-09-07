import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel

DURATION = 20  # seconds
SAMPLE_RATE = 16000  # Whisper wants 16kHz

print("Recording in 3... 2... 1...")
audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
sd.wait()
sf.write("test_recording.wav", audio, SAMPLE_RATE)
print("Recording saved. Transcribing...")

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("test_recording.wav")

print(f"Detected language: {info.language}")
for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")