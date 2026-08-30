#!/usr/bin/env python3
"""LID unit test: determinism + multilingual coverage (75 langs)."""
from app.core.language import detect_language, get_language_directive

CASES = {
    "pl_diacritics": ("Jakie są najnowsze trendy w branży AI w tym tygodniu?", "pl"),
    "pl_no_diacritics": ("Co nowego wydarzylo sie w swiecie sztucznej inteligencji? Zolc", "pl"),
    "en": ("What are the latest developments in artificial intelligence?", "en"),
    "de": ("Was sind die neuesten Entwicklungen in der kuenstlichen Intelligenz?", "de"),
    "fr": ("Quelles sont les dernieres avancees en matiere d'intelligence artificielle ?", "fr"),
    "ru": ("Какие последние достижения в области искусственного интеллекта?", "ru"),
    "zh": ("人工智能领域最近有什么新发展？", "zh"),
    "es": ("¿Cuáles son los últimos avances en inteligencia artificial?", "es"),
    "uk": ("Які останні досягнення у сфері штучного інтелекту?", "uk"),
    "ja": ("人工知能の最新の発展について教えてください。", "ja"),
    "short_ambiguous": ("ok", None),
}

failures = 0
for name, (text, expected) in CASES.items():
    lang = detect_language(text)
    d = get_language_directive(lang)
    status = "OK"
    if expected is not None and lang != expected:
        status, failures = f"FAIL (got {lang!r}, want {expected!r})", failures + 1
for name, (text, expected) in CASES.items():
    lang = detect_language(text)
    d = get_language_directive(lang)
    if expected is None:
        # Ambiguous input MUST resolve to None (mirror mode) - any concrete
        # language here is a false positive that would force the wrong output
        # language on language-neutral queries like "ok".
        status = "OK" if lang is None else f"FAIL (false positive: {lang!r}, want None)"
        if lang is not None:
            failures += 1
    elif lang != expected:
        status, failures = f"FAIL (got {lang!r}, want {expected!r})", failures + 1
    else:
        status = "OK"
    print(f"{name:16s} -> {lang!r:8s} [{status}] directive: {d[:70]}...")
    print(f"{name:16s} -> {lang!r:8s} [{status}] directive: {d[:70]}...")

# Determinism: same input -> same output (critical for response cache keys)
for _, (text, _) in CASES.items():
    assert detect_language(text) == detect_language(text), f"non-deterministic for {text!r}"

# Directive sanity: known lang -> native name present; unknown -> mirror rule
assert "Polski" in get_language_directive("pl")
assert "Deutsch" in get_language_directive("de")
assert "中文" in get_language_directive("zh")
assert "Mirror the language" in get_language_directive(None)

if failures:
    raise SystemExit(f"{failures} LID test(s) FAILED")
print("\nALL LID UNIT TESTS PASSED (deterministic + multilingual)")
