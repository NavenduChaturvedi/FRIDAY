# Tools

Each `.py` file here is one tool FRIDAY's brain can call. Drop a file in, it's
picked up on the next launch — nothing else to edit. Files starting with `_`
are ignored (see `_template.py`).

## Shape

```python
TOOL = {
    "name": "get_time",                    # snake_case, unique, <= 48 chars
    "description": "...",                   # the model reads this to decide when to call it
    "parameters": {                        # JSON Schema, an object
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "..."},
        },
        "required": [],
    },
}

def run(timezone: str = "") -> str:
    return "It's 4:05 in the morning in Tokyo."
```

- `run` is called with the arguments the model supplied, matched to your
  parameter names. Return a short plain sentence — it goes back to the model
  and usually on to the speaker.
- Don't raise. Catch your own errors and return a sentence explaining the
  problem. (The loader catches anything you miss, but the message is uglier.)
- Need to speak later (a timer, a reminder)? Add `notify` to your signature:
  `def run(seconds: int, notify=None)`. You get a `Callable[[str], None]`;
  whatever you pass it is spoken at the start of the next turn.
- Need to run something from startup (a background checker), not just when
  called? Define `on_load(notify)` at module level — it's called once at
  launch for enabled tools. `set_reminder.py` uses this. Add a `toolbox`
  parameter (`on_load(notify, toolbox=None)`) to also receive the `Toolbox`,
  so the checker can call other tools — `schedule.py` builds the briefing
  that way.

## Destructive actions

If a tool can lose data or do something outward-facing, gate it in the `TOOL`
dict:

```python
TOOL = {
    ...
    "confirm": {"action": ["clear"]},          # or  "confirm": True
    "mutates": {"action": ["add", "clear"]},   # or  "mutates": True
}

def confirm_prompt(action="", **_) -> str:      # optional — the spoken phrasing
    return "That wipes all your notes for good." if action == "clear" else ""
```

- **`confirm`** — FRIDAY parks the call, tells the user what it will do, and
  runs it only if the *next* turn is a clear "yes". "no" (or anything
  unrelated) drops it. Disable the whole gate with `FRIDAY_CONFIRM_ACTIONS=false`.
- **`mutates`** — before the call, `state/` is snapshotted (one level).
  "undo" / "undo that" restores it. List the *writing* actions only, not
  reads, or every `list` will clobber the undo point.

Both take `True` (every call) or `{param: [values]}` (only matching calls).
`notes` and `memory` already use this; copy their shape for a `delete_file` or
`send_message`.

## Bundled

**Answers & lookups**
| Tool | What it does |
|---|---|
| `get_time` | current time, local or any IANA timezone |
| `calculate` | safe arithmetic — sums, percentages, `sqrt`/`sin`/`log`/… |
| `get_weather` | current conditions + today's range for a city (Open-Meteo) |
| `web_search` | DuckDuckGo search, returns snippets to summarise |
| `get_news` | recent headlines, optionally about a topic |
| `wikipedia_lookup` | short factual summary of a topic |
| `define_word` | word definitions (Wiktionary) |

**Doing things**
| Tool | What it does |
|---|---|
| `set_timer` | countdown; announces itself when it fires (not saved) |
| `reminder` | one-shot time-based reminder; **survives restart**, checked in the background |
| `schedule` | **recurring** jobs (daily/weekdays/…); `task="briefing"` reads the morning rundown. Survives restart. |
| `notes` | transient scratchpad — add / list / remove / clear |
| `memory` | durable facts about the user; feeds the system prompt (remember / recall / forget / list) |
| `open_url` | open a web page in the default browser |
| `launch_app` | open a desktop app by name |
| `clipboard` | read or set the system clipboard |
| `random_choice` | coin / dice / random number / pick from a list |

**The machine & files**
| Tool | What it does |
|---|---|
| `system_status` | CPU, memory, disk, battery |
| `read_file` | read a local text file so FRIDAY can answer about it |
| `find_files` | search for files by name under a folder |

## Enabling / disabling

All tools in this directory are on by default. To run a subset, set
`FRIDAY_TOOLS_ENABLED` in `.env` to a comma-separated list of names.

## Notes

- Timers, reminders and scheduled jobs fire on time but are only *spoken* on
  FRIDAY's next turn (when you next talk to her).
- `schedule`'s morning briefing is a plain template (`_compose_briefing`) —
  time, `get_weather` for `FRIDAY_HOME_CITY`, today's `reminder`s, `notes`,
  optional `get_news`. No LLM, so it works with the model unloaded. It reaches
  the other tools via the `toolbox` its `on_load(notify, toolbox=None)` is
  handed.
- `set_timer` is in-process and gone on restart; `reminder` is written to
  `state/` and survives.
- The acting tools here are reversible or low-stakes (open an app, set the
  clipboard, write a note). Anything that deletes or sends must set `confirm`
  (see "Destructive actions" above) — don't ship one without it.
- Extra packages some tools need (all in `requirements.txt`): `ddgs`
  (`web_search`, `get_news`), `tzdata` (`get_time` on Windows), `psutil`
  (`system_status`), `pyperclip` (`clipboard`), `dateparser` (`reminder`).
  A missing package disables just that tool, with a spoken note.
