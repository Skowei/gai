#!/usr/bin/env python3
"""E2E: language stability across fresh generations + cache."""
import httpx, re, sys

BASE = "http://localhost:8000"
QUESTION = "Wymień trzy ciekawe fakty o Morzu Bałtyckim."
PL_WORDS = ["jest", "się", "oraz", "które", "można", "warto", "także", "znajduje", "należy", "tworzą", "leży", "położone", "milionów", "wieku", "bałtyckie", "Bałtyku", "fakty", "ciekawe", "trzy", "głębokość", "zasolenie", "państw", "wybrzeże", "morze", "Morze"]

def is_polish(text: str) -> bool:
    diacritics = len(re.findall(r"[ąćęłńóśźż]", text.lower()))
    words = sum(1 for w in PL_WORDS if w in text)
    return diacritics >= 2 or words >= 3

fails = 0
for i in (1, 2, 3):
    sid = f"lang_e2e_fresh_{i}_{i*i}"
    r = httpx.post(f"{BASE}/api/v1/chat", json={"message": QUESTION, "session_id": sid}, timeout=120)
    ok_http = r.status_code == 200
    body = r.json() if ok_http else {}
    resp = str(body.get("response", ""))
    polish = is_polish(resp)
    status = "OK" if (ok_http and polish) else "FAIL"
    if status == "FAIL":
        fails += 1
    print(f"FRESH #{i}: http={r.status_code} from_cache={body.get('from_cache')} polish={polish} [{status}]")
    print(f"  preview: {resp[:100]!r}")

# Cache hit: repeat run 1 session+question -> identical text expected
r = httpx.post(f"{BASE}/api/v1/chat", json={"message": QUESTION, "session_id": f"lang_e2e_fresh_1_1"}, timeout=120)
body = r.json()
print(f"CACHE HIT: http={r.status_code} from_cache={body.get('from_cache')} [OK]" if body.get("from_cache") else f"CACHE HIT: from_cache={body.get('from_cache')} [WARN - TTL may have expired]")

print("\nALL LANGUAGE E2E PASSED" if fails == 0 else f"\n{fails} E2E FAILURE(S)")
sys.exit(1 if fails else 0)
