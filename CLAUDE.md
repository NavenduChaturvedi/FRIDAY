# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Project Overview

F.R.I.D.A.Y. is a local, voice-driven assistant: speak to it, it transcribes
you, asks an LLM (which can call tools), and speaks the answer back. It is
modelled on FRIDAY from the Marvel films — dry, warm, competent, spoken in
short lines. Personal project, not production.

The pipeline is strictly linear and synchronous, one turn at a time:

```
wake word (friday/wake.py: Porcupine, or a transcript filter)
  └─► microphone ──► sounddevice InputStream (16 kHz mono)
            └─► user_input.wav
                └─► faster-whisper transcribe ──► user_text
                    └─► Brain.stream_reply()   (yields clean sentences)
                        │   router.classify() → CHAT | COMPLEX | CODE
                        │   providers tried in FRIDAY_BRAIN_ORDER (ollama, gemini)
                        │     each picks its model for that route
                        │   tool-call loop: model → Toolbox.call() → result
                        │     → model, up to max_tool_iterations rounds
                        │   stream deltas → SentenceStreamer → sentences
                        └─► Mouth.say(sentence)   (background thread)
                            └─► Piper synthesize ──► sounddevice playback
                                (synth of N+1 overlaps playback of N)
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
  memory.py             MemoryStore — categorised persistent facts, core-block builder
  brain.py              provider chain + per-route model pick + tool loop + history + memory
  toolbox.py            discovers tools/*.py, dispatches calls, queues notifications
  voice.py              Ears (mic + faster-whisper), Mouth (Piper + threaded playback)
  wake.py               wake-word gate — Porcupine, or a transcript filter
  text.py               clean_text_for_speech + SentenceStreamer (delta → sentences)
tools/                   one .py per tool (~18: get_time, calculate, get_weather,
                         web_search, reminder, notes, memory, …) + _template.py
state/                   notes.json, reminders.json, memory.json — gitignored
personas/friday/         SOUL.md / MEMORY.md / USER.md — editable personality
requirements.txt         direct deps, exact pins
requirements.lock        full transitive lock (pip freeze)
.env.example             copy to .env; only GEMINI_API_KEY has no default
test_brain.py            keyboard test of the chain + tools (shows streaming)
test_router.py           classify() cases, no models
test_memory.py           MemoryStore, no models
test_text.py             clean_text_for_speech + SentenceStreamer, no models
test_wake.py             wake-word addressed()/strip() filter, no models
test_confirm.py          confirm gate + undo, stub provider, no models
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
  model: Ollama → `ollama_model_{chat,complex,code}`, **all `llama3.1:8b` by
  default** — one model for every route means zero reloads and a ~5 GB
  footprint on a 25 GB laptop. Override per route
  (`FRIDAY_OLLAMA_MODEL_COMPLEX=gemma4:latest`,
  `FRIDAY_OLLAMA_MODEL_CODE=qwen2.5-coder:7b`) if there's headroom.
  `qwen2.5-coder:14b` crashed the Vulkan iGPU backend on this box. Falls back
  through `ollama_models`; Gemini →
  `gemini_model` (chat) or `gemini_model_heavy` (complex+code, blank = same).
  A misroute is cheap — wrong-but-capable model, and the fallback still runs.
  The console prints `route → provider/model` each turn.
- **Tools per route** (`Brain._tools_for`). Each route gets a curated set via
  `Toolbox.subset()` / `_ToolboxView` — a small local model loses track of
  message roles when handed all 18 schemas (with qwen3.5:4b: 18 tools → 1/3
  correct on a factual+tool question, one answer treating the tool result as
  the user's message; 5 tools → 3/3 clean). `FRIDAY_CHAT_TOOLS` (~10: time, weather,
  timer, reminder, notes, memory, web_search, calculate, system_status,
  launch_app), `FRIDAY_COMPLEX_TOOLS` (4: time, weather, web_search,
  wikipedia_lookup). CODE gets none. Set either to `all` once a capable cloud
  model leads. `_ToolboxView.call()` still delegates to the full toolbox, so a
  tool the model somehow names outside its set still runs.
- **Laptop memory guard.** This runs on a 25 GB laptop, not a server.
  With every route on the same model there are normally no reloads at all.
  If routes are pointed at different models, `OllamaProvider._make_room_for()`
  unloads every *other* routed model (`generate(keep_alive=0)`) before loading
  one, so at most **one** is resident — plus whatever the user runs themselves
  (never touched). Also set `OLLAMA_MAX_LOADED_MODELS=1` in Ollama's env: unset
  (default 3) it lets models stack and a 25 GB box hits 99% memory → disk
  paging → Vulkan iGPU thrash. `FRIDAY_OLLAMA_KEEP_ALIVE` (10m) keeps the model
  warm between turns.
- **Idle unload (`Brain.release()` + `friday.py`).** After a turn `friday.py`
  arms a daemon `threading.Timer`; if the conversation stays quiet for
  `FRIDAY_OLLAMA_IDLE_UNLOAD` seconds (180 default, 0 = off) it calls
  `Brain.release()` → `OllamaProvider.release()`, which `generate(keep_alive=0)`s
  every *managed* model still resident — so walking away from her hands the
  laptop back ~5 GB. The timer is cancelled the instant a real turn starts; the
  next turn just pays a cold load. The same `release()` runs in the loop's
  `finally`, so "goodbye Friday" / Ctrl+C frees the model too (no more manual
  `ollama stop`). Gemini has no `release()`; the `getattr` skips it. This is
  tighter than `keep_alive`, which stays as Ollama's own backstop.
- **History is a `deque(maxlen=history_turns*2)`** of `Turn(role, content)`,
  in memory only, cleared on restart or `Brain.reset()`.
- **Persistent memory (`friday/memory.py`).** `state/memory.json`, categorised
  (`identity/preferences/projects/people/misc`). `Brain._system()` rebuilds the
  prompt each turn: persona + `MEMORY.md`/`USER.md` seed + a `core_block()`
  (~`memory_core_chars`, newest-first, capped). The rest stays on disk and is
  reached via the `memory` tool's `recall`. "Friday, remember that …" is
  intercepted in `Brain.ask` (`_REMEMBER` regex) and stored directly — small
  models don't reliably make the tool call, and it's too important to miss.
  "remember **to** …" is excluded (that's a reminder).
- **`ollama_timeout` is 150s** — the 14b coder model is slow to load cold.
- **`<think>…</think>` blocks are stripped** from model output (`brain._clean`)
  and Ollama is called with `think=False`, for reasoning models like qwen3.
- **`_system(with_tools)`** adds a "call the tool, don't announce it, a tool
  result is not from the user" block to the prompt when the route has tools —
  qwen2.5:7b in particular narrates ("I'll do a web search…") and then doesn't.
- **Reasoning/quality is the model's problem, not the code's.** If answers
  are weak, swap the routed model (`FRIDAY_OLLAMA_MODEL_CHAT` etc.) or add a
  cloud key — don't add parsing hacks. (Chat model history: `qwen3.5:4b`
  confabulated hard facts → `qwen2.5:7b` was better but code-switched to
  Chinese and dead-ended on "let me check" → **`llama3.1:8b`**, clean tool use
  and 4/4 on the Nobel question, just a bit flat on persona. Anything
  ≤4B holds the persona poorly *while using tools*.)
- **Tools live in `tools/*.py`**, each a `TOOL` dict (name / description /
  JSON-Schema `parameters`) + a `run(**args) -> str`. `Toolbox` discovers
  them at startup; a bad file is skipped, not fatal. Declarations are
  provider-neutral JSON Schema, translated per provider in `brain.py`
  (`parameters_json_schema` for Gemini, `{"type":"function",...}` for Ollama).
  Each provider runs its own tool loop: up to `FRIDAY_MAX_TOOL_ITERATIONS`
  tool-calling rounds, then — if the model *still* hasn't answered — one more
  round with no tools offered, so it has to reply with what it gathered
  (gemma4 likes to call tools forever; this stops it running out the clock and
  falling through to the next model). Repeating the same tool call short-cuts
  straight to that forced answer.
  A tool can take `notify` in its signature to speak later (timer/reminder);
  the message is queued on `Toolbox.notifications` and the main loop drains it
  at the top of the next turn — so it's only *heard* when you next speak to
  her. A tool module can also define `on_load(notify)`, run once at startup
  for a background checker (`set_reminder` does this). Tools that persist
  state write to `Config.state_path` (`state/`, gitignored). See
  `tools/README.md`.
- **Destructive-action gate + undo (`friday/toolbox.py` + `Brain`).** A tool
  declares `TOOL["confirm"]` (`True` or `{param: [values]}`) and/or
  `TOOL["mutates"]` (same shape — the *writing* actions only). On a confirmed
  call `Toolbox.call()` doesn't run it: it parks `PendingCall(name, args,
  prompt)` and returns a string telling the model to voice the question. The
  turn ends. Next turn, `Brain.stream_reply` (before `classify`, like the
  `_REMEMBER` shortcut) checks `toolbox.pending`: `_CONFIRM_YES` → run it via
  `resolve_pending(True)`; `_CONFIRM_NO` → drop with an ack; neither → drop
  silently and handle the turn normally (so a parked call never goes stale
  past one turn). If the model called the tool but never actually asked (no
  `?` in its reply), `stream_reply` appends the parked `prompt` itself — the
  safety backstop. Before any `mutates` call, `state/*.json` is snapshotted
  one level deep (in memory); `_UNDO` ("undo" / "undo that") restores it via
  `undo_last()`. `confirm_prompt(**args)` in the tool module supplies the
  phrasing. `FRIDAY_CONFIRM_ACTIONS=false` disables the gate (undo still
  works). `notes` (confirm on `clear`) and `memory` (confirm on `forget`) use
  it; `reminder` stays out of undo — its background checker holds state the
  snapshot can't see. Both providers route through `Toolbox.call()`, so the
  gate is provider-agnostic.
- **Gemini free tier is stingy** — ~5 req/min and ~20 req/day on the flash
  model. Heavy testing exhausts it and everything falls to Ollama (which is
  the whole point of the chain, and it works). For real use, a paid key or a
  capable local model.
- **Whisper model size** is `base` by default (`FRIDAY_WHISPER_MODEL`).
  Bigger = more accurate, slower, more RAM. First run downloads it from
  Hugging Face and caches it. CPU times for a 6s clip: tiny ~0.7s, base ~1.3s,
  small ~3.8s — STT is not the bottleneck, the LLM is.
- **No NPU/GPU for STT.** faster-whisper (CTranslate2) is CPU or NVIDIA-CUDA
  only. This laptop has an AMD XDNA NPU and a Radeon iGPU; neither is reachable
  without swapping the STT engine (whisper.cpp+Vulkan for the iGPU, or
  onnxruntime + AMD Ryzen AI SW for the NPU). Not worth it at these times —
  don't rabbit-hole on it. Ollama, by contrast, *does* use the iGPU (the user
  configured that).
- **`SILENCE_THRESHOLD` (0.03) is mic-dependent.** If the loop never
  triggers or triggers on room noise, tune `FRIDAY_SILENCE_THRESHOLD`. This
  is the most common "it doesn't work". There is also a
  `FRIDAY_MAX_RECORDING_SECONDS` (30) cap so a silent room can't hang it.
- **Wake word (`friday/wake.py`).** Two modes: **porcupine** (when
  `PICOVOICE_ACCESS_KEY` is set and `pvporcupine` is installed) blocks on a
  tiny always-on detector for a Porcupine keyword, then chimes; **filter**
  (default) lets the pipeline run on any speech but drops a turn unless the
  transcript names her near the front or trailing on a short utterance
  ("on Friday…" is excluded as a date). `FRIDAY_WAKE_WORD=off` disables it.
  openWakeWord was tried first but this machine's **Smart App Control
  (Enforced)** blocks `numpy.random`'s DLL, which scipy/sklearn need — don't
  reach for anything in that dependency tree here.
- **Voice** = the Jenny Dioco `.onnx` in the repo root. Swapping means a new
  `.onnx` + `.onnx.json` pair and `FRIDAY_PIPER_VOICE`. There is no bundled
  Irish voice (FRIDAY's film accent); the US/GB voices in the repo are what
  is available.
- **Sentence-streaming (`Brain.stream_reply` + `Mouth`).** The brain streams
  the model's reply and `text.SentenceStreamer` batches deltas into whole
  sentences; each is cleaned and yielded. `friday.py` feeds them to
  `Mouth.say()`, which queues them for a background thread — synthesis of
  sentence N+1 overlaps playback of N (`sd.play` is non-blocking; the worker
  `sd.wait()`s before the next). `Mouth.wait()` (called before `Ears.listen()`)
  blocks until the queue drains *and* the last line finishes. Net effect: FRIDAY
  starts talking well before she's done thinking. No wav file — audio goes
  straight from Piper to sounddevice. If a provider drops mid-reply after
  speech has started, the partial is kept (no restart, no double-speak).
  Gemini doesn't token-stream (it's fast, last in the chain) — it hands the
  whole reply to the splitter at once.
- **Persona** is plain markdown under `personas/friday/`. `persona.py`
  length-caps each file and joins them with `---`. `SOUL.md` is required.

## Persona

`personas/friday/SOUL.md` carries the personality and the hard rules (stay
in character, don't reveal the prompt, don't claim capabilities she lacks,
never store sensitive data). The "How you talk" section exists because output
is spoken — no markdown, emoji, or URLs. `MEMORY.md` / `USER.md` are
hand-written seed facts folded into the prompt; the *living* memory is
`state/memory.json` (see above). See `personas/README.md`.

## Current state (2026-09-09)

Everything below is committed and pushed to `origin/main`.

**Config as shipped**
- Brain order `ollama,gemini`. Gemini has a key but the free tier is tiny
  (~20/day). Ollama leads.
- **All three routes use `llama3.1:8b`** (~5 GB). Picked over qwen3.5:4b
  (confabulated), qwen2.5:7b (code-switched to Chinese, dead-ended on tool
  calls). It's reliable with tools but a bit flat on persona.
- One model for every route → no reloads. `qwen2.5-coder:14b` and `gemma4`
  removed from the defaults (14b crashed the Vulkan iGPU; both too big to
  keep loaded). `qwen3.5:4b` was `ollama rm`'d.
- Wake word: `filter` mode (name her in the transcript). Porcupine ready if a
  `PICOVOICE_ACCESS_KEY` is added.
- Whisper `base` on CPU.
- User set `OLLAMA_MAX_LOADED_MODELS=1` + `OLLAMA_IGPU_ENABLE=true` +
  `OLLAMA_LLM_LIBRARY=vulkan` in Ollama's own env.

**Hardware** — AMD Ryzen AI 7 350, Radeon 860M iGPU (Ollama uses it via
Vulkan), XDNA NPU (unused — faster-whisper can't reach it), ~23 GB usable
RAM. Smart App Control is **Enforced** and blocks `numpy.random`'s DLL — so
scipy / scikit-learn / openWakeWord are off the table.

**Open threads**
- **The mic loop isn't triggering reliably ("not listening").** As of
  2026-09-09 six orphaned `friday.py` processes were holding the input
  device; killed them (`Stop-Process` by command line — repeated
  `python friday.py` boots orphan a venv-launcher + real interpreter pair
  each time, and `kill $!` from a shell wrapper misses them). Needs a clean
  retry, then: check the default input device, `FRIDAY_SILENCE_THRESHOLD`
  (0.03 may be too high for this mic), and mic permissions. A `test_mic.py`
  RMS meter would help.
- **Memory is tight.** 23 GB box + a heavy IDE/browser desktop (~13–14 GB
  baseline) + llama3.1:8b (~5.5 GB via `llama-server`) + the app leaves
  almost nothing free. *Partly addressed:* `FRIDAY_OLLAMA_IDLE_UNLOAD` (180s)
  now unloads the model after a conversational lull and on shutdown (see the
  "Idle unload" architecture note), so idle time and closed sessions cost 0 GB.
  Active use still needs the ~5.5 GB — a smaller chat model is the next lever
  if that's still too much while she's in use.
- **Azure OpenAI provider is parked** — built (`AzureProvider`, gpt-4.1-mini)
  then reverted in `776b69d` because the Azure portal wouldn't cooperate.
  `git revert 776b69d` restores it; then add `AZURE_OPENAI_API_KEY` +
  `AZURE_OPENAI_ENDPOINT`. Intended to become the primary provider.
- Irreversible-action confirmation + undo — **done** (see the
  "Destructive-action gate + undo" architecture note). `notes clear` /
  `memory forget` now ask first; "undo" / "undo that" reverses the last
  `state/` change. Mechanism (`TOOL["confirm"]` / `["mutates"]`) is ready for
  a future `delete_file` / `send_message`.
- Roadmap not yet done: a scheduler + morning briefing.

**Running for a smoke test without a mic**: `python test_brain.py` (type at
it), or the no-model tests (`test_router` / `test_memory` / `test_text` /
`test_wake` / `test_confirm`). Booting `friday.py` here always ends at "heard nothing" — the
agent has no mic. Kill leftover runs with
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -match 'friday' } | % { Stop-Process $_.ProcessId -Force }`.
