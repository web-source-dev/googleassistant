"""Local command parser — English and Turkish speech to apps, sites, search, or close."""

from __future__ import annotations

import re
from typing import Any

from src.targets import ALIASES, KNOWN_TARGETS

_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
_FOLD = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "â": "a",
    "î": "i",
    "û": "u",
})

# Turkish wake phrases (longest first). "asistan youtube aç"
DEFAULT_WAKE_PHRASES = (
    "hey asistan",
    "uyan asistan",
    "asistanim",
    "asistanım",
    "asistanı",
    "asistan",
    "assistant",
    "asistam",
    "asistans",
)

OPEN_VERBS = (
    "open up",
    "open",
    "launch",
    "start",
    "run",
    "go to",
    "goto",
    "play",
    "show me",
    "show",
    "bring up",
    "pull up",
    "take me to",
    "acar misin",
    "acar mısın",
    "acsana",
    "açsana",
    "baslat",
    "başlat",
    "goster",
    "göster",
    "oynat",
    "ac",
    "aç",
)

SEARCH_PHRASES = (
    "search for",
    "look up",
    "google for",
    "google da ara",
    "google'da ara",
    "sunu ara",
    "şunu ara",
    "search",
    "ara",
)

CLOSE_PHRASES = (
    "close",
    "quit",
    "kill",
    "exit",
    "stop",
    "kapat",
    "kapa",
    "cik",
    "çık",
)

FILLER_PREFIXES = (
    "please",
    "can you",
    "could you",
    "would you",
    "i want to",
    "i wanna",
    "i need to",
    "lutfen",
    "lütfen",
    "bakar misin",
    "bakar mısın",
    "bana",
    "just",
)

FILLER_WORDS = frozenset({
    "the", "a", "an", "my", "please",
    "lutfen", "lütfen", "bir", "su", "şu", "bana",
})

_SUFFIXES = (
    "leri", "lari",     "nın", "nin", "nun", "nün",
    "dan", "den", "tan", "ten",
    "lar", "ler",
    "yı", "yi", "yu", "yü", "ya", "ye",
    "nı", "ni", "nu", "nü",
    "ın", "in", "un", "ün",
    "ı", "i", "u", "ü",
)


def parse_command(text: str) -> dict[str, Any]:
    """Turn spoken text into an open / search / close intent."""
    cleaned = _normalize_text(text)
    if not cleaned:
        return _unknown("")

    search = _extract_after(cleaned, SEARCH_PHRASES)
    if search is not None:
        matched = _match_target(search)
        if matched:
            return _open_intent(matched)
        if search in {"google", ""}:
            return _open_intent("google")
        if search:
            return {
                "action": "search",
                "target": search,
                "speak": f"Searching for {search}",
            }

    if cleaned.startswith("google "):
        query = cleaned[7:].strip()
        if query and _match_target(query) is None:
            return {
                "action": "search",
                "target": query,
                "speak": f"Searching for {query}",
            }

    close = _extract_after(cleaned, CLOSE_PHRASES)
    if close is not None:
        target = _match_target(close) or close
        if not target:
            return _unknown(cleaned)
        return {
            "action": "close",
            "target": target,
            "speak": f"Closing {target}",
        }

    remainder = _strip_open_verbs(_strip_fillers(cleaned))
    for candidate in (remainder, cleaned, _strip_suffixes(remainder)):
        matched = _match_target(candidate)
        if matched:
            return _open_intent(matched)

    return _unknown(remainder or cleaned)


def _unknown(target: str) -> dict[str, Any]:
    return {
        "action": "unknown",
        "target": target,
        "speak": "I did not understand that command.",
    }


def _open_intent(target: str) -> dict[str, Any]:
    known = KNOWN_TARGETS.get(target, {})
    intent: dict[str, Any] = {
        "action": "open",
        "target": target,
        "speak": f"Opening {target}",
    }
    if known.get("url"):
        intent["url"] = known["url"]
    return intent


def turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def fold_tr(text: str) -> str:
    return turkish_lower(text).translate(_FOLD)


def split_wake_command(text: str, extra_wake: str = "") -> tuple[str | None, str]:
    """If a Turkish wake phrase is present, return (wake, command after it)."""
    cleaned = _normalize_text(text)
    if not cleaned:
        return None, ""

    phrases = list(DEFAULT_WAKE_PHRASES)
    extra = _normalize_text(extra_wake)
    if extra and extra not in phrases:
        phrases.insert(0, extra)
    phrases.sort(key=len, reverse=True)

    folded_words = fold_tr(cleaned).split()
    words = cleaned.split()

    for phrase in phrases:
        phrase_words = fold_tr(phrase).split()
        n = len(phrase_words)
        if n == 0 or n > len(folded_words):
            continue
        for i in range(len(folded_words) - n + 1):
            if folded_words[i : i + n] == phrase_words:
                rest = " ".join(words[i + n :])
                return phrase, rest
    return None, cleaned


def _normalize_text(text: str) -> str:
    text = turkish_lower(text).strip().replace("'", " ").replace("’", " ")
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _strip_fillers(text: str) -> str:
    changed = True
    while changed and text:
        changed = False
        for prefix in FILLER_PREFIXES:
            if text == prefix or text.startswith(prefix + " "):
                text = text[len(prefix) :].strip()
                changed = True
                break
    words = [w for w in text.split() if w not in FILLER_WORDS]
    return " ".join(words)


def _strip_open_verbs(text: str) -> str:
    for verb in OPEN_VERBS:
        if text == verb:
            return ""
        if text.startswith(verb + " "):
            return text[len(verb) :].strip()
        if text.endswith(" " + verb):
            return text[: -(len(verb) + 1)].strip()
    return text


def _strip_suffixes(text: str) -> str:
    if not text:
        return text
    words = text.split()
    last = words[-1]
    folded_last = fold_tr(last)
    for suffix in _SUFFIXES:
        folded_suffix = fold_tr(suffix)
        if folded_last.endswith(folded_suffix) and len(folded_last) - len(folded_suffix) >= 3:
            words[-1] = last[: -len(suffix)] if last.lower().endswith(suffix) else last[: -len(folded_suffix)]
            return " ".join(w for w in words if w)
    return text


def _extract_after(text: str, phrases: tuple[str, ...]) -> str | None:
    folded = fold_tr(text)
    for phrase in phrases:
        folded_phrase = fold_tr(phrase)
        if folded == folded_phrase:
            return ""
        if folded.startswith(folded_phrase + " "):
            return text[len(phrase) :].strip() if text.startswith(phrase) else text[len(folded_phrase) :].strip()
        if folded.endswith(" " + folded_phrase):
            return text[: -(len(phrase) + 1)].strip()
    return None


def _match_target(text: str) -> str | None:
    if not text:
        return None

    folded = fold_tr(text)
    compact = folded.replace(" ", "")
    candidates: list[tuple[int, str, str]] = []

    for alias, canonical in ALIASES.items():
        candidates.append((len(alias), alias, canonical))
    for name in KNOWN_TARGETS:
        candidates.append((len(name), name, name))

    candidates.sort(key=lambda item: item[0], reverse=True)

    seen: set[str] = set()
    for _, alias, canonical in candidates:
        key = f"{alias}|{canonical}"
        if key in seen:
            continue
        seen.add(key)
        alias_folded = fold_tr(alias)
        alias_compact = alias_folded.replace(" ", "")
        if folded == alias_folded or compact == alias_compact or _has_phrase(folded, alias_folded):
            return canonical
    return None


def _has_phrase(text: str, phrase: str) -> bool:
    if " " in phrase:
        return phrase in text
    if len(phrase) < 3:
        return False
    return re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text) is not None
