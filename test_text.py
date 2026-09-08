"""Text helpers smoke test — clean_text_for_speech + SentenceStreamer.

    python test_text.py
"""

from friday.text import SentenceStreamer, clean_text_for_speech

fails = 0


def check(got, want, label):
    global fails
    ok = got == want
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        print(f"       got  {got!r}\n       want {want!r}")


print("clean_text_for_speech:")
check(clean_text_for_speech("**Done.** Lights `off`."), "Done. Lights off.", "markdown")
check(clean_text_for_speech("- one\n- two"), "one two", "bullets")
check(clean_text_for_speech("See [the docs](http://x) now"), "See the docs now", "links")
check(clean_text_for_speech("2 * 3 = 6"), "2 * 3 = 6", "math survives")
check(clean_text_for_speech("the range is 2 - 3 hours"), "the range is 2 - 3 hours", "minus survives")
check(clean_text_for_speech("hi 🦾 there"), "hi there", "emoji")
check(clean_text_for_speech("--- The Process 1. Heat it"), "The Process 1. Heat it", "leading rule")
check(clean_text_for_speech("**2. Grind:** use a burr grinder"), "Grind: use a burr grinder", "bold list item")


def stream(text, size=3):
    s = SentenceStreamer()
    out = []
    for i in range(0, len(text), size):
        out += s.feed(text[i : i + size])
    return out + s.flush()


print("\nSentenceStreamer:")
check(
    stream("The short answer is no. The long answer is also no."),
    ["The short answer is no.", "The long answer is also no."],
    "two sentences",
)
check(stream("Done. Lights off. Anything else?"),
      ["Done.", "Lights off.", "Anything else?"], "terse lines")
check(stream("It costs 3.5 dollars. Cheap!"),
      ["It costs 3.5 dollars.", "Cheap!"], "decimal not split")
check(stream("Ask Dr. Smith. He knows."),
      ["Ask Dr. Smith.", "He knows."], "abbreviation not split")
check(stream("first... second... third."),
      ["first...", "second...", "third."], "ellipsis pauses")
check(stream("No boundary here yet"), ["No boundary here yet"], "trailing fragment")
check(stream("Steps: 1. Boil water. 2. Add tea. 3. Wait."),
      ["Steps: 1. Boil water.", "2. Add tea.", "3. Wait."], "numbered list not over-split")

print("\n" + ("all passed" if not fails else f"{fails} failed"))
raise SystemExit(1 if fails else 0)
