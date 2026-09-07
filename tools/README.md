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

## Bundled

| Tool | What it does |
|---|---|
| `get_time` | current time, local or any IANA timezone |
| `set_timer` | countdown timer; announces itself when it fires |
| `web_search` | DuckDuckGo search, returns snippets for the model to summarise |

## Enabling / disabling

All tools in this directory are on by default. To run a subset, set
`FRIDAY_TOOLS_ENABLED` in `.env` to a comma-separated list of names.

## Notes

- A timer fires on schedule but is only *spoken* on FRIDAY's next turn (when
  you next talk to her). Timers don't survive a restart.
- `web_search` needs the `ddgs` package (in `requirements.txt`); `get_time`
  needs `tzdata` on Windows.
