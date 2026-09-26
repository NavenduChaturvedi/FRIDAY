# F.R.I.D.A.Y.

A local, voice-driven assistant modelled on FRIDAY from the Marvel films: dry,
warm, competent, and brief. You talk to her, she transcribes you, thinks with
an LLM that can call tools, and answers out loud.

Speech-to-text and text-to-speech run on your machine, and so does the model
by default (Ollama). Gemini is an optional cloud fallback. There's no agent
framework: the whole app is this repo plus a handful of pip packages.

> Personal project, built and tested on a Windows laptop. Not production software.

## How it works

```
wake word ─► microphone (16 kHz) ─► faster-whisper ─► text
   ─► router: CHAT | COMPLEX | CODE ─► pick a model for that route
   ─► LLM (Ollama → Gemini fallback) ⇄ tools, a few rounds at most
   ─► reply streamed sentence by sentence ─► Piper TTS ─► speakers
```

- **Streaming speech.** She starts talking after the first sentence. While
  one sentence plays, the next is being synthesised.
- **Provider chain.** Providers are tried in order (`ollama,gemini` by default)
  and the first reply wins. If Ollama is down or there's no Gemini key, that
  provider is skipped.
- **Per-route models.** A quick keyword router decides whether a request is
  chat, reasoning-heavy or code, and each route can use its own model and its
  own set of tools.
- **Persistent memory.** Say "Friday, remember that…" and the fact is saved to
  `state/memory.json`. The most relevant facts go into every prompt.
- **Safety net.** Destructive actions such as clearing notes or forgetting
  memories ask first. "Undo that" reverses the last change.
- **Easy on a laptop.** The model is unloaded after a few minutes of quiet and
  on exit, so an idle FRIDAY uses no model RAM.

## Tools

Each tool is a single Python file in `tools/`, and new ones are picked up
automatically. See [`tools/README.md`](tools/README.md).

| Tool | What it does |
|---|---|
| `get_time`, `set_timer`, `reminder`, `schedule` | Time, countdowns, one-off reminders, recurring jobs and a spoken morning briefing |
| `get_weather`, `get_news`, `web_search`, `wikipedia_lookup`, `define_word` | Looking things up |
| `notes`, `memory` | A scratchpad, plus long-term facts about you |
| `calculate`, `random_choice` | Maths, coin flips and dice |
| `launch_app`, `open_url`, `find_files`, `read_file`, `clipboard`, `system_status` | Controlling the desktop |

## Getting started

**Requirements:** Windows, **Python 3.12** (3.13+ has no ctranslate2 or
onnxruntime wheels yet), a mic and speakers, and [Ollama](https://ollama.com)
with at least one model pulled.

```powershell
git clone https://github.com/NavenduChaturvedi/FRIDAY.git
cd FRIDAY
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

ollama pull llama3.1:8b
copy .env.example .env      # optional: add GEMINI_API_KEY
```

The Piper voice model (`en_GB-jenny_dioco-medium.onnx`) is stored with Git LFS.
Run `git lfs pull` if it comes down as a tiny pointer file.

### Run

```powershell
python friday.py            # console voice loop
python friday_ui.py         # the same pipeline with a small Tkinter control panel
python test_brain.py        # type at the brain; no audio needed
```

To put a shortcut on your Desktop:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-shortcut.ps1
```

Start a request with her name ("Friday, what's the weather in London?"). To
stop, say "goodbye Friday", press Ctrl+C, or click **Quit** in the UI.

## Configuration

Every setting is an environment variable with a sensible default. All of them
are documented in [`.env.example`](.env.example). The ones you're most likely
to change:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Enables the Gemini fallback |
| `FRIDAY_BRAIN_ORDER` | `ollama,gemini` | Order the providers are tried in |
| `FRIDAY_OLLAMA_MODEL_CHAT` / `_COMPLEX` / `_CODE` | `llama3.1:8b` | Model for each route |
| `FRIDAY_WAKE_WORD` | `friday` | Name that gets her attention (`off` = respond to everything) |
| `PICOVOICE_ACCESS_KEY` | none | Turns on a real always-on wake-word detector (Porcupine) |
| `FRIDAY_SILENCE_THRESHOLD` | `0.03` | Mic sensitivity; tune this if she never hears you or reacts to room noise |
| `FRIDAY_WHISPER_MODEL` | `base` | STT size: `tiny` / `base` / `small` / … |
| `FRIDAY_HOME_CITY` | none | City for the morning briefing's weather line |
| `FRIDAY_OLLAMA_IDLE_UNLOAD` | `180` | Seconds of quiet before the model is unloaded (`0` = never) |

## Personality

Her personality is plain markdown in [`personas/friday/`](personas/friday/).
`SOUL.md` holds her voice and hard rules, and `USER.md` / `MEMORY.md` hold
seed facts. Edit them to change how she talks. See
[`personas/README.md`](personas/README.md).

## Project layout

```
friday.py / friday_ui.py   entrypoints (console loop / desktop UI)
friday/                    config, router, brain, memory, toolbox, voice, wake word
tools/                     one file per tool
personas/friday/           personality markdown
state/                     notes, reminders, memory, schedule (created at runtime, gitignored)
test_*.py                  tests; most need no models or audio
```

## Tests

These run without models, a mic or speakers:

```powershell
python test_router.py; python test_memory.py; python test_text.py
python test_wake.py; python test_confirm.py; python test_schedule.py; python test_ui.py
```

`test_whisper.py` and `test_piper.py` are smoke tests for real audio hardware.

## Troubleshooting

- **She never responds.** Check your default input device, then lower
  `FRIDAY_SILENCE_THRESHOLD`. Also make sure no leftover `friday.py` process is
  holding the mic.
- **"No brain available."** Start Ollama (`ollama serve`) and pull a
  model, or add a Gemini key.
- **Slow first reply.** The model is loading cold after the idle unload. Later
  turns are fast.
