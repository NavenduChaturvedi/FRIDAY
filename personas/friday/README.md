# Friday persona

The voice and personality of F.R.I.D.A.Y. as loaded by `friday/persona.py`.
Three files, all read on every launch:

- `SOUL.md` — who Friday is, how she speaks, what she will not do. Capped at
  ~6000 chars.
- `MEMORY.md` — things she has learned about the user that should survive
  across sessions. Capped at ~2500 chars.
- `USER.md` — who the user is: name, pronouns, timezone, free-form notes.
  Capped at ~1500 chars.

## Customizing

- Different name? Edit `USER.md`, change "boss" to what you want. Picked up
  on the next launch.
- Different pronouns? Same place.
- Want Friday to know something about you (your job, your project, the dog)?
  Add a line under "Notes" in `USER.md`.
- Change her voice? That's not a persona thing — set `FRIDAY_PIPER_VOICE` in
  `.env` (see `.env.example`).

## What you should NOT edit

- The "Hard rules" section of `SOUL.md` — those keep Friday from being
  talked into something she shouldn't do.
- The "Voice rules" section — the reply is *spoken*, so markdown, emoji, and
  links all sound terrible read aloud.

## Memory

Friday can read `MEMORY.md` but not yet write to it. To have her carry
something across restarts, add a dated bullet by hand. In-conversation
"remember this" is coming later.
