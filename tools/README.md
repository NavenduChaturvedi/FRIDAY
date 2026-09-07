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
  launch for enabled tools. `set_reminder.py` uses this.

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
| `reminder` | time-based reminder; **survives restart**, checked in the background |
| `notes` | persistent scratchpad — add / list / remove / clear |
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

- Timers and reminders fire on schedule but are only *spoken* on FRIDAY's
  next turn (when you next talk to her).
- `set_timer` is in-process and gone on restart; `reminder` is written to
  `state/` and survives.
- Every acting tool here is reversible or low-stakes (open an app, set the
  clipboard, write a note). A real confirmation gate for irreversible actions
  is still on the roadmap — don't add a tool that deletes or sends without
  one.
- Extra packages some tools need (all in `requirements.txt`): `ddgs`
  (`web_search`, `get_news`), `tzdata` (`get_time` on Windows), `psutil`
  (`system_status`), `pyperclip` (`clipboard`), `dateparser` (`reminder`).
  A missing package disables just that tool, with a spoken note.
