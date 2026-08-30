"""
Enterprise Language Identification (LID)
=========================================
Deterministic language detection for any-of-75-languages support.

Architecture (degradation chain):
    1. lingua-py   - 75 languages, best accuracy on short chat texts,
                     returns None when confidence is too low
    2. langdetect  - 55 languages (Google language-detection port),
                     seeded for determinism
    3. None        - undetectable ("ok", single numbers) -> caller falls back
                     to a language-mirroring instruction for the LLM

The system prompt stays in English (most reliable for local 8B models);
the RESPONSE language is enforced via an explicit directive that uses the
NATIVE language name ("Deutsch", "Français", "中文") - native names carry
a much stronger signal for small local models than English names.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Optional dependencies: graceful degradation ---------------------------
_LINGUA = None
_LANGDETECT = None

try:
    from lingua import Language, LanguageDetectorBuilder  # type: ignore
    _LINGUA = {
        "builder": LanguageDetectorBuilder,
        "languages": Language,
    }
except ImportError:
    logger.warning("[LID] lingua-language-detector not installed - falling back to langdetect")

try:
    import langdetect  # type: ignore
    from langdetect import DetectorFactory  # type: ignore
    # Deterministic results across runs (langdetect is stochastic by default)
    DetectorFactory.seed = 0
    _LANGDETECT = langdetect
except ImportError:
    logger.warning("[LID] langdetect not installed - LID will return None (mirror mode)")

# lingua detector is expensive to build (loads 75 language models) -> build ONCE
# minimum_relative_distance=0.5 -> returns None for ambiguous texts instead of
# guessing (guards against e.g. "ok" being classified as Zulu).
_LINGUA_DETECTOR = None
if _LINGUA:
    try:
        _LINGUA_DETECTOR = (
            _LINGUA["builder"]
            .from_all_languages()
            .with_minimum_relative_distance(0.5)
            .build()
        )
        logger.info("[LID] lingua detector initialized (75 languages, distance=0.5)")
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"[LID] lingua init failed: {e}")
        _LINGUA = None


# --- ISO 639-1 code -> native (autonym) language name -----------------------
# Native names are stronger output-language anchors for small local models.
NATIVE_NAMES = {
    "pl": "Polski", "en": "English", "de": "Deutsch", "fr": "Français",
    "es": "Español", "it": "Italiano", "pt": "Português", "nl": "Nederlands",
    "ru": "Русский", "uk": "Українська", "zh": "中文", "ja": "日本語",
    "ko": "한국어", "ar": "العربية", "hi": "हिन्दी", "cs": "Čeština",
    "sk": "Slovenčina", "sv": "Svenska", "no": "Norsk", "da": "Dansk",
    "fi": "Suomi", "tr": "Türkçe", "el": "Ελληνικά", "he": "עברית",
    "hu": "Magyar", "ro": "Română", "bg": "Български", "hr": "Hrvatski",
    "sr": "Српски", "vi": "Tiếng Việt", "th": "ไทย", "id": "Bahasa Indonesia",
    "lt": "Lietuvių", "lv": "Latviešu", "et": "Eesti", "sl": "Slovenščina",
    "fa": "فارسی", "sw": "Kiswahili", "tl": "Tagalog", "bn": "বাংলা",
}


def _normalize_iso(raw) -> Optional[str]:
    """
    Normalize lingua's ISO code to a lowercase 639-1/639-3 string.

    Version-robust: lingua may return an enum whose str() is
    'IsoCode639_1.PL', a plain string 'pl', or an enum with .value.
    """
    if raw is None:
        return None
    code = getattr(raw, "value", None) or getattr(raw, "name", None) or str(raw)
    code = str(code).split(".")[-1].strip().lower()
    return code if code and code.isalpha() else None


def detect_language(text: str) -> Optional[str]:
    """
    Detect the language of *text*.

    Returns:
        ISO 639-1 code (e.g. "pl", "de", "zh") or None when the language
        cannot be determined reliably (too short / ambiguous input).

    Deterministic: identical input always yields the identical result
    (required for correct response-cache behaviour).
    """
    if not text or not text.strip():
        return None

    # 1) lingua-py: best on short texts, None on low confidence by design
    if _LINGUA_DETECTOR is not None and len(text.strip()) >= 4:
        try:
            language = _LINGUA_DETECTOR.detect_language_of(text)
            if language is not None:
                return _normalize_iso(getattr(language, "iso_code_639_1", None)) \
                    or _normalize_iso(getattr(language, "iso_code_639_3", None))
        except Exception as e:
            logger.debug(f"[LID] lingua failed: {e}")

    # 2) langdetect fallback (seeded -> deterministic)
    # Same length guard as lingua: on ultra-short inputs ("ok", "hej")
    # langdetect confidently returns garbage (e.g. 'sk' for "ok").
    if _LANGDETECT is not None and len(text.strip()) >= 4:
        try:
            probs = _LANGDETECT.detect_langs(text)
            if probs and probs[0].prob >= 0.50:
                return probs[0].lang
        except Exception:
            # langdetect raises on no-features texts (digits, symbols)
            pass

    return None


def get_language_directive(lang_code: Optional[str]) -> str:
    """
    Build the output-language directive for the finalization prompt.

    * Known language  -> explicit, native-name anchored directive.
    * None            -> deterministic mirror instruction.
    """
    if not lang_code:
        return (
            "LANGUAGE REQUIREMENT (HIGHEST PRIORITY): Mirror the language of "
            "the user's message exactly. Write your ENTIRE final response in "
            "the same language the user used. Never mix languages."
        )

    native = NATIVE_NAMES.get(lang_code)
    if not native:
        # Unknown code -> safe generic directive with the code itself
        native = lang_code.upper()

    return (
        f"LANGUAGE REQUIREMENT (HIGHEST PRIORITY): The user's message is written in "
        f"{native} (ISO: {lang_code}). Your ENTIRE final response MUST be written "
        f"ONLY in {native}. All explanations, reasoning and formatting MUST be in "
        f"{native}. If any context material below is in English, translate the facts "
        f"into natural {native} before answering. Never mix languages. "
        f"Code snippets, identifiers, URLs and product names stay in their original form."
    )