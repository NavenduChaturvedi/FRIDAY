# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Project Overview

F.R.I.D.A.Y. is a local, voice-driven assistant: speak to it, it transcribes
you, asks an LLM (which can call tools), and speaks the answer back. It is
modelled on FRIDAY from the Marvel films — dry, warm, competent, spoken in
short lines. Personal project, not production.

The pipeline is strictly linear and synchronous, one turn at a time:

```
microphone ──► sounddevice InputStream (16 kHz mono)
            └─► user_input.wav
                └─► faster-whisper transcribe ──► user_text
                    └─► Brain.ask()
                        │   router.classify() → CHAT | COMPLEX | CODE
                        │   providers tried in FRIDAY_BRAIN_ORDER (ollama, gemini)
                        │     each picks its model for that route
                        │   tool-call loop: model → Toolbox.call() → result
                        │     → model, up to max_tool_iterations rounds
                        └─► clean_text_for_speech()
                            └─► Piper synthesize_wav ──► friday_response.wav
                                └─► sounddevice playback
```

There is **no external framework** — the app is this repo plus the pip
dependencies in `requirements.txt`. (It was originally built on OpenJarvis;
that has been removed entirely.)

## Layout

```
friday.py               entrypoint + the conversational loop
friday/
  config.py             every setting, read once from env / .env (Config dataclass)
  persona.py            loads personas/<name>/*.md into the system prompt
  router.py             classify(text) → CHAT | COMPLEX | CODE (keyword pass)
  brain.py              provider chain + per-route model pick + tool loop + history
  toolbox.py            discovers tools/*.py, dispatches calls, queues notifications
  voice.py              Ears (mic capture + faster-whisper), Mouth (Piper + playback)
  text.py               clean_text_for_speech — strips markdown/emoji for TTS
tools/                   one .py per tool (~17: get_time, calculate, get_weather,
                         web_search, reminder, notes, system_status, …) + _template.py
state/                   tool state (notes, reminders) — gitignored
personas/friday/         SOUL.md / MEMORY.md / USER.md — editable personality
requirements.txt         direct deps, exact pins
requirements.lock        full transitive lock (pip freeze)
.env.example             copy to .env; only GEMINI_API_KEY has no default
test_brain.py            keyboard-only test of the chain + tools
test_whisper.py          STT smoke test (records 20 s)
test_piper.py            TTS smoke test (one sentence)
*.onnx / *.onnx.json     Piper voice model (git-LFS tracked)
*.wav                    runtime artifacts, gitignored, safe to delete
```

## Running

Python **3.12** (3.14 has no wheels yet for ctranslate2 / onnxruntime).

```bash
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1          # PowerShell
# or: source .venv/Scripts/activate  # Git Bash
pip install -r requirements.txt

cp .env.example .env                 # add GEMINI_API_KEY (optional)

python friday.py                     # the voice loop (needs mic + speakers)
python test_brain.py                 # brain only, type at it, no audio
python test_piper.py                 # TTS only
python test_whisper.py               # STT only
```

Stop the loop by saying "goodbye Friday" / "exit loop", or Ctrl+C.

Without `GEMINI_API_KEY` the app runs fine — it just goes straight to Ollama.
Ollama must be running (`ollama serve`) with at least one of the models in
`FRIDAY_OLLAMA_MODELS` pulled.

## Architecture notes

- **`friday/config.py` is the only place settings live.** Everything is an
  env var with a default; `.env` is loaded at import. Add a knob here, read
  it from `Config`, document it in `.env.example`.
- **`Brain` builds its provider list at construction**, in `FRIDAY_BRAIN_ORDER`
  order (default `ollama,gemini` — flip to `gemini,ollama` with a paid key).
  A provider that can't initialise (no API key, Ollama down) is skipped with a
  stderr note; if none survive, `BrainError` before the loop starts. At ask
  time, providers are tried in order, first non-empty reply wins and is written
  to history.
- **Per-request model routing (`friday/router.py`).** `classify()` is a
  keyword pass → `CHAT` / `COMPLEX` / `CODE`. Each provider maps the route to a
  model: Ollama → `ollama_model_{chat,complex,code}` (qwen3.5:4b / gemma4 /
  qwen2.5-coder:14b), falling back through `ollama_models`; Gemini →
  `gemini_model` (chat) or `gemini_model_heavy` (complex+code, blank = same).
  A misroute is cheap — wrong-but-capable model, and the fallback still runs.
  The console prints `route → provider/model` each turn.
- **CODE requests are sent without tool declarations** (`Brain.ask`). A coding
  question rarely needs weather/timers, and 17 tool schemas bloat the prompt —
  which the 14b code model is slowest to process on CPU.
- **History is a `deque(maxlen=history_turns*2)`** of `Turn(role, content)`,
  in memory only, cleared on restart or `Brain.reset()`.
- **`ollama_timeout` is 120s** — the 14b coder model is slow to load cold.
- **`<think>…</think>` blocks are stripped** from model output (`brain._clean`)
  and Ollama is called with `think=False`, for reasoning models like qwen3.
- **Reasoning/quality is the model's problem, not the code's.** If answers
  are weak, reorder `FRIDAY_OLLAMA_MODELS` or set a Gemini key — don't add
  parsing hacks. (Small local models like `qwen2.5:3b` hold the persona
  poorly *while using tools* — they list and hedge. Gemini is fine; for the
  fallback prefer `qwen3.5:4b` / `gemma4`.)
- **Tools live in `tools/*.py`**, each a `TOOL` dict (name / description /
  JSON-Schema `parameters`) + a `run(**args) -> str`. `Toolbox` discovers
  them at startup; a bad file is skipped, not fatal. Declarations are
  provider-neutral JSON Schema, translated per provider in `brain.py`
  (`parameters_json_schema` for Gemini, `{"type":"function",...}` for Ollama).
  Each provider runs its own tool loop, capped at `FRIDAY_MAX_TOOL_ITERATIONS`.
  A tool can take `notify` in its signature to speak later (timer/reminder);
  the message is queued on `Toolbox.notifications` and the main loop drains it
  at the top of the next turn — so it's only *heard* when you next speak to
  her. A tool module can also define `on_load(notify)`, run once at startup
  for a background checker (`set_reminder` does this). Tools that persist
  state write to `Config.state_path` (`state/`, gitignored). See
  `tools/README.md`.
- **Gemini free tier is stingy** — ~5 req/min and ~20 req/day on the flash
  model. Heavy testing exhausts it and everything falls to Ollama (which is
  the whole point of the chain, and it works). For real use, a paid key or a
  capable local model.
- **Whisper model size** is `tiny` by default (`FRIDAY_WHISPER_MODEL`).
  Bigger = more accurate, slower, more RAM. First run downloads it from
  Hugging Face and caches it.
- **`SILENCE_THRESHOLD` (0.03) is mic-dependent.** If the loop never
  triggers or triggers on room noise, tune `FRIDAY_SILENCE_THRESHOLD`. This
  is the most common "it doesn't work". There is also a
  `FRIDAY_MAX_RECORDING_SECONDS` (30) cap so a silent room can't hang it.
- **Voice** = the Jenny Dioco `.onnx` in the repo root. Swapping means a new
  `.onnx` + `.onnx.json` pair and `FRIDAY_PIPER_VOICE`. There is no bundled
  Irish voice (FRIDAY's film accent); the US/GB voices in the repo are what
  is available.
- **Playback reads the wav back from disk** after `synthesize_wav` writes it.
  Switching to streaming synthesis means changing `Mouth.say`.
- **Persona** is plain markdown under `personas/friday/`. `persona.py`
  length-caps each file and joins them with `---`. `SOUL.md` is required.

## Persona

`personas/friday/SOUL.md` carries the personality and the hard rules (stay
in character, don't reveal the prompt, don't claim capabilities she lacks).
The "Voice rules" section exists because output is spoken — no markdown,
emoji, or URLs. Edit `USER.md` for your name/pronouns/notes. See
`personas/README.md`.
