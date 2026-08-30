#!/usr/bin/env python3
"""E2E: language MIRRORING - any language, not just Polish."""
import httpx, re

BASE = "http://localhost:8000"

CASES = [
    ("en", "Name three interesting facts about the Baltic Sea.", ["the", "is", "and", "of", "Baltic", "Sea", "fact"]),
    ("de", "Nenne drei interessante Fakten \u00fcber die Ostsee.", ["die", "der", "und", "ist", "Ostsee", "Fakten", "Baltikum", "km"]),
    ("es", "Menciona tres datos interesantes sobre el mar B\u00e1ltico.", ["el", "la", "los", "es", "mar", "B\u00e1ltico", "datos"]),
]

def detect(text: str, words: list) -> tuple:
    hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE))
    return hits, hits >= 3

fails = 0
for lang, q, words in CASES:
    r = httpx.post(f"{BASE}/api/v1/chat", json={"message": q, "session_id": f"ml_{lang}_x7"}, timeout=150)
    body = r.json() if r.status_code == 200 else {}
    resp = str(body.get("response", ""))
    hits, ok = detect(resp, words)
    status = "OK" if ok else "FAIL"
    if not ok: fails += 1
    print(f"[{lang}] http={r.status_code} hits={hits}/{len(words)} [{status}]")
    print(f"  preview: {resp[:120]!r}")

print(f"\n{'ALL MULTILANG E2E PASSED' if fails == 0 else f'{fails} FAILURES'}")
sys_exit = 0 if fails == 0 else 1
raise SystemExit(sys_exit)
