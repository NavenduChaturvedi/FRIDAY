"""Router smoke test — no models, just the keyword classifier.

    python test_router.py
"""

from friday.router import Route, classify

CASES = {
    Route.CHAT: [
        "hey friday what's up",
        "how are you doing today",
        "good morning",
        "what time is it in tokyo",
        "set a timer for ten minutes",
        "what's the weather like in oslo",
        "tell me a joke",
        "remind me to call mum at 6",
    ],
    Route.COMPLEX: [
        "explain why the sky is blue",
        "how does a transformer work",
        "compare postgres and mongodb for a chat app",
        "walk me through the causes of the 2008 crash",
        "plan my week around three deadlines",
        "what are the trade-offs between renting and buying",
    ],
    Route.CODE: [
        "write a python function to reverse a linked list",
        "my script throws a KeyError, help me debug it",
        "fix this regex ^[a-z]+$",
        "how do I reverse a string in python",
        "review this git rebase",
        "why is my async function not awaiting",
    ],
}

fails = 0
for expected, prompts in CASES.items():
    for p in prompts:
        got = classify(p)
        mark = "ok " if got == expected else "FAIL"
        if got != expected:
            fails += 1
        print(f"  {mark}  want {expected.value:8s} got {got.value:8s}  {p}")

print()
print("all passed" if not fails else f"{fails} misclassified")
raise SystemExit(1 if fails else 0)
