# Personas

A persona is FRIDAY's personality, kept as plain markdown so you can edit it
without touching code. Each persona is a directory here:

```
personas/<name>/
  SOUL.md     required — who she is, how she speaks, her hard rules
  MEMORY.md   optional — facts to carry across sessions
  USER.md     optional — who you are (name, pronouns, timezone, notes)
```

`friday/persona.py` reads these on every launch, length-caps each file, and
concatenates them into the system prompt sent to the brain. Only `SOUL.md`
is required.

## Switching personas

Set `FRIDAY_PERSONA=<name>` in `.env` to load `personas/<name>/` instead of
`personas/friday/`.

## Editing

Just edit the files and relaunch. If you want a shorter cap or a different
layout, change `_FILES` in `friday/persona.py`.
