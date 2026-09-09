"""F.R.I.D.A.Y. with a desktop control panel.

    pythonw friday_ui.py     # no console — what the desktop shortcut runs
    python  friday_ui.py     # console too, handy for debugging

Same pipeline as ``friday.py`` — wake word, mic, faster-whisper, the routed
brain with tools, Piper — but driven from a small always-on Tkinter window:
the current state, a live mic-level bar, the running transcript, a box to type
at her instead of speaking, and Mute / Stop / Quit.

``friday.py`` (the plain console loop) is left untouched; this is a second
entry point over the same ``friday/`` package. The assistant runs on a worker
thread and talks to the window through two queues — Tkinter is only ever
touched on the main thread.

Porcupine always-on wake is skipped here (that needs the console loop); in
filter mode spoken input is still gated by the wake word exactly as in the
console.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging: under pythonw.exe there is no console and ``sys.stdout`` is None,
# which makes the first bare print() in any component raise. Tee everything to
# friday_ui.log (and to the real streams when they exist).
# ---------------------------------------------------------------------------
_LOG_PATH = Path(__file__).with_name("friday_ui.log")


class _Tee:
    def __init__(self, *streams) -> None:
        self._streams = [s for s in streams if s is not None]

    def write(self, s: str) -> int:
        for st in self._streams:
            try:
                st.write(s)
            except Exception:  # noqa: BLE001 — a dead stream mustn't crash a print
                pass
        return len(s)

    def flush(self) -> None:
        for st in self._streams:
            try:
                st.flush()
            except Exception:  # noqa: BLE001
                pass


def _install_logging() -> None:
    try:
        f = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)
    except OSError:
        f = None
    for name in ("stdout", "stderr"):
        real = getattr(sys, name)
        try:
            real.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        setattr(sys, name, _Tee(real, f))


import tkinter as tk  # noqa: E402
from tkinter.scrolledtext import ScrolledText  # noqa: E402

from friday.brain import Brain, BrainError  # noqa: E402
from friday.config import Config  # noqa: E402
from friday.text import clean_text_for_speech  # noqa: E402
from friday.toolbox import Toolbox  # noqa: E402
from friday.voice import Ears, Mouth  # noqa: E402
from friday.wake import Wake  # noqa: E402

# -- palette -------------------------------------------------------------
BG = "#0b0e14"
PANEL = "#141a24"
INK = "#c8d0da"
MUTED = "#6b7686"
USER = "#8ab4f8"
FRIDAY = "#39c5cf"
WARN = "#e0a45e"
BAD = "#e06c75"
GOOD = "#8fce7a"

_STATES = {
    "starting": ("Starting…", MUTED),
    "idle": ("Idle", MUTED),
    "listening": ("Listening", FRIDAY),
    "thinking": ("Thinking", WARN),
    "speaking": ("Speaking", GOOD),
    "error": ("Error", BAD),
    "closing": ("Shutting down…", MUTED),
}


def _hint(wake: Wake) -> str:
    if wake.mode == "porcupine":
        return f"say “{wake.keyword}” or just type"
    if wake.mode == "filter":
        return f"say “{wake.word}, …” or just type"
    return "speak or type"


# ===========================================================================
# Worker — the assistant loop, off the UI thread
# ===========================================================================
class Worker(threading.Thread):
    def __init__(self, ui_q: queue.Queue, cmd_q: queue.Queue) -> None:
        super().__init__(daemon=True, name="friday-worker")
        self.ui_q = ui_q
        self.cmd_q = cmd_q
        self._muted = False
        self._quit = False
        self._interrupt = False
        self.brain: Brain | None = None
        self._mouth: Mouth | None = None

    # -- helpers ------------------------------------------------------
    def _emit(self, *msg) -> None:
        self.ui_q.put(msg)

    def _drain_cmds(self) -> str | None:
        """Apply mute/stop/quit; return a typed line if one was queued."""
        typed = None
        try:
            while True:
                kind, *rest = self.cmd_q.get_nowait()
                if kind == "quit":
                    self._quit = True
                    if self._mouth is not None:
                        self._mouth.stop()
                elif kind == "mute":
                    self._muted = bool(rest[0])
                elif kind == "stop":
                    self._interrupt = True
                elif kind == "text":
                    typed = rest[0]
        except queue.Empty:
            pass
        return typed

    def _interruptible(self) -> bool:
        """True when the recorder should bail — a command is waiting."""
        return self._quit or not self.cmd_q.empty()

    def _say_and_wait(self, mouth: Mouth, line: str) -> None:
        self._emit("transcript", "friday", line)
        mouth.say(line)
        mouth.wait()

    # -- lifecycle --------------------------------------------------
    def run(self) -> None:
        try:
            cfg, toolbox, ears, mouth, wake, brain = self._setup()
        except Exception as exc:  # noqa: BLE001
            self._emit("state", "error", "couldn't start — see friday_ui.log")
            self._emit("transcript", "error", str(exc))
            import traceback

            traceback.print_exc()
            self._emit("closed")
            return
        try:
            self._loop(cfg, toolbox, ears, mouth, wake, brain)
        finally:
            try:
                brain.release()
            except Exception:  # noqa: BLE001
                pass
            self._emit("closed")

    def _setup(self):
        cfg = Config()
        print(f"Waking F.R.I.D.A.Y. …  {cfg.summary()}")
        self._emit("notice", cfg.summary())
        toolbox = Toolbox(cfg.tools_path, cfg.tools_enabled, confirm=cfg.confirm_actions)
        for skip in toolbox.skipped:
            self._emit("transcript", "notice", f"tool skipped — {skip}")
        ears = Ears(cfg)
        mouth = Mouth(cfg)
        self._mouth = mouth
        wake = Wake(cfg)
        brain = Brain(cfg, toolbox)
        self.brain = brain
        self._emit("threshold", cfg.silence_threshold)
        self._emit("ready", f"{wake.describe()}  ·  {_hint(wake)}")
        self._emit("state", "idle", _hint(wake))
        return cfg, toolbox, ears, mouth, wake, brain

    # -- the turn loop --------------------------------------------
    def _loop(self, cfg, toolbox, ears, mouth, wake, brain) -> None:
        while not self._quit:
            for note in toolbox.drain_notifications():
                self._emit("transcript", "friday", note)
                mouth.say(clean_text_for_speech(note))
            mouth.wait()
            if self._quit:
                break

            typed = self._drain_cmds()
            if self._quit:
                break

            if typed is not None and typed.strip():
                user_text = typed.strip()
                self._emit("transcript", "you", user_text)
            elif self._muted:
                self._emit("state", "idle", "muted — type to her, or un-mute")
                try:  # park until something happens, but stay responsive
                    self.cmd_q.put(self.cmd_q.get(timeout=0.5))
                except queue.Empty:
                    pass
                continue
            else:
                self._emit("state", "listening")
                heard = ears.listen(
                    on_level=lambda r: self._emit("level", r),
                    should_stop=self._interruptible,
                )
                self._emit("level", 0.0)
                if self._quit:
                    break
                if not heard:
                    self._emit("state", "idle", _hint(wake))
                    continue
                if any(p in heard.lower() for p in cfg.exit_phrases):
                    self._emit("transcript", "you", heard)
                    self._say_and_wait(mouth, "Powering down. Catch you later.")
                    self._quit = True
                    break
                if not wake.addressed(heard):
                    self._emit("transcript", "notice", f"(not for me: {heard})")
                    self._emit("state", "idle", _hint(wake))
                    continue
                user_text = wake.strip(heard)
                self._emit("transcript", "you", user_text)

            if any(p in user_text.lower() for p in cfg.exit_phrases):
                self._say_and_wait(mouth, "Powering down. Catch you later.")
                self._quit = True
                break

            self._interrupt = False
            self._emit("state", "thinking")
            spoke = False
            try:
                for sentence in brain.stream_reply(user_text):
                    if self._interrupt:
                        mouth.stop()
                        self._emit("transcript", "notice", "(stopped)")
                        break
                    if not spoke:
                        spoke = True
                        self._emit("state", "speaking")
                    self._emit("transcript", "friday", sentence)
                    mouth.say(sentence)
            except BrainError as exc:
                self._emit("transcript", "error", f"brain error: {exc}")
                mouth.say("I lost my train of thought there. Say that again?")

            self._drain_cmds()  # pick up mute/quit that landed mid-reply
            mouth.wait()
            self._emit("state", "idle", _hint(wake))


# ===========================================================================
# App — the window, main thread only
# ===========================================================================
class App(tk.Tk):
    POLL_MS = 40

    def __init__(self, ui_q: queue.Queue, cmd_q: queue.Queue) -> None:
        super().__init__()
        self.ui_q = ui_q
        self.cmd_q = cmd_q
        self._muted = False
        self._threshold = 0.03
        self._closing = False

        self.title("F.R.I.D.A.Y.")
        self.geometry("470x640")
        self.minsize(390, 470)
        self.configure(bg=BG)
        try:
            self.tk.call("tk", "scaling", 1.3)
        except tk.TclError:
            pass

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.POLL_MS, self._pump)

    # -- layout ------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 14}

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", pady=(14, 6), **pad)
        self._dot = tk.Canvas(head, width=14, height=14, bg=BG, highlightthickness=0)
        self._dot.pack(side="left", pady=(4, 0))
        self._dot_id = self._dot.create_oval(2, 2, 12, 12, fill=MUTED, outline="")
        box = tk.Frame(head, bg=BG)
        box.pack(side="left", padx=8)
        self._state_lbl = tk.Label(
            box, text="Starting…", bg=BG, fg=INK,
            font=("Segoe UI Semibold", 13), anchor="w",
        )
        self._state_lbl.pack(anchor="w")
        self._sub_lbl = tk.Label(
            box, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w"
        )
        self._sub_lbl.pack(anchor="w")

        self._meter = tk.Canvas(self, height=10, bg=PANEL, highlightthickness=0)
        self._meter.pack(fill="x", pady=(4, 10), **pad)
        self._meter_fill = self._meter.create_rectangle(0, 0, 0, 10, fill=FRIDAY, outline="")
        self._meter_tick = self._meter.create_line(0, 0, 0, 10, fill=MUTED)

        self._log = ScrolledText(
            self, bg=PANEL, fg=INK, insertbackground=INK, relief="flat",
            font=("Segoe UI", 10), wrap="word", padx=10, pady=8, height=10,
        )
        self._log.pack(fill="both", expand=True, **pad)
        self._log.tag_config("you", foreground=USER, font=("Segoe UI Semibold", 10))
        self._log.tag_config("friday", foreground=FRIDAY)
        self._log.tag_config("notice", foreground=MUTED, font=("Segoe UI", 9, "italic"))
        self._log.tag_config("error", foreground=BAD)
        self._log.configure(state="disabled")

        entry_row = tk.Frame(self, bg=BG)
        entry_row.pack(fill="x", pady=(10, 4), **pad)
        self._entry = tk.Entry(
            entry_row, bg=PANEL, fg=INK, insertbackground=INK, relief="flat",
            font=("Segoe UI", 10),
        )
        self._entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._entry.bind("<Return>", lambda _e: self._send())
        self._send_btn = self._button(entry_row, "Send", self._send, FRIDAY)
        self._send_btn.pack(side="left", padx=(6, 0))

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", pady=(4, 14), **pad)
        self._mute_btn = self._button(btn_row, "Mute mic", self._toggle_mute, INK)
        self._mute_btn.pack(side="left")
        self._button(btn_row, "Stop", self._stop, INK).pack(side="left", padx=6)
        self._button(btn_row, "Quit", self._on_close, BAD).pack(side="right")

        self._entry.focus_set()

    def _button(self, parent, text, cmd, fg):
        return tk.Button(
            parent, text=text, command=cmd, bg=PANEL, fg=fg,
            activebackground="#1f2733", activeforeground=fg, relief="flat",
            font=("Segoe UI", 9), padx=12, pady=5, borderwidth=0,
            highlightthickness=0, cursor="hand2",
        )

    # -- actions ------------------------------------------------
    def _send(self) -> None:
        text = self._entry.get().strip()
        if not text or self._closing:
            return
        self._entry.delete(0, "end")
        self.cmd_q.put(("text", text))

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self.cmd_q.put(("mute", self._muted))
        self._mute_btn.config(
            text="Unmute mic" if self._muted else "Mute mic",
            fg=WARN if self._muted else INK,
        )

    def _stop(self) -> None:
        self.cmd_q.put(("stop",))

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._set_state("closing", "")
        self._entry.config(state="disabled")
        self.cmd_q.put(("quit",))
        self.after(4000, self.destroy)  # hard fallback if the worker hangs

    # -- queue pump -------------------------------------------
    def _pump(self) -> None:
        last_level = None
        try:
            while True:
                kind, *rest = self.ui_q.get_nowait()
                if kind == "level":
                    last_level = rest[0]
                elif kind == "state":
                    self._set_state(rest[0], rest[1] if len(rest) > 1 else None)
                elif kind == "transcript":
                    self._append(rest[0], rest[1])
                elif kind == "notice":
                    self._sub_lbl.config(text=rest[0])
                elif kind == "threshold":
                    self._threshold = rest[0] or 0.03
                elif kind == "ready":
                    self._sub_lbl.config(text=rest[0])
                elif kind == "closed":
                    self.destroy()
                    return
        except queue.Empty:
            pass
        if last_level is not None:
            self._draw_level(last_level)
        self.after(self.POLL_MS, self._pump)

    def _set_state(self, name: str, sub: str | None) -> None:
        label, colour = _STATES.get(name, (name.title(), INK))
        self._state_lbl.config(text=label, fg=colour)
        self._dot.itemconfig(self._dot_id, fill=colour)
        if sub is not None:
            self._sub_lbl.config(text=sub)
        if name != "listening":
            self._draw_level(0.0)

    def _draw_level(self, rms: float) -> None:
        w = self._meter.winfo_width() or 1
        full = max(self._threshold * 4.0, 1e-4)
        frac = min(rms / full, 1.0)
        self._meter.coords(self._meter_fill, 0, 0, w * frac, 10)
        self._meter.itemconfig(
            self._meter_fill, fill=FRIDAY if rms >= self._threshold else MUTED
        )
        tick = w * min(self._threshold / full, 1.0)
        self._meter.coords(self._meter_tick, tick, 0, tick, 10)

    def _append(self, who: str, text: str) -> None:
        prefix = {"you": "You  ", "friday": "FRIDAY  "}.get(who, "")
        self._log.configure(state="normal")
        if self._log.index("end-1c") != "1.0":
            self._log.insert("end", "\n")
        self._log.insert("end", prefix, (who,))
        self._log.insert("end", text, (who,) if who in ("notice", "error") else ())
        self._log.see("end")
        self._log.configure(state="disabled")


def main() -> int:
    _install_logging()  # before anything prints (pythonw has no stdout)
    ui_q: queue.Queue = queue.Queue()
    cmd_q: queue.Queue = queue.Queue()
    worker = Worker(ui_q, cmd_q)
    app = App(ui_q, cmd_q)
    worker.start()
    try:
        app.mainloop()
    finally:
        cmd_q.put(("quit",))
        worker.join(timeout=6)
    return 0


if __name__ == "__main__":
    sys.exit(main())
