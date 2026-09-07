"""Memory store smoke test — no models, uses a throwaway file.

    python test_memory.py
"""

import tempfile
from pathlib import Path

from friday.memory import MemoryStore

tmp = Path(tempfile.mkdtemp()) / "memory.json"
m = MemoryStore(tmp)

assert m.is_empty()
assert m.core_block() == ""

m.add("Name is Sam", "identity")
m.add("Prefers metric units", "preferences")
m.add("Building a voice assistant called Friday", "projects")
m.add("Has a dog named Biscuit", "people")
m.add("Prefers metric units", "preferences")  # dup — should be ignored

entries = m.all_entries()
assert len(entries) == 4, entries

core = m.core_block(1000)
print("--- core block ---")
print(core)
assert "Sam" in core and "Biscuit" in core

hits = m.search("dog")
assert len(hits) == 1 and "Biscuit" in hits[0].value, hits
print("\nsearch('dog') ->", hits[0].value)

removed = m.forget("metric")
assert removed == ["Prefers metric units"], removed
assert len(m.all_entries()) == 3
print("forget('metric') ->", removed)

# budget is respected
for i in range(50):
    m.add(f"Random fact number {i} padded padded padded", "misc")
assert len(m.core_block(300)) <= 300
print("\nbudget cap ok")

print("\nall passed")
