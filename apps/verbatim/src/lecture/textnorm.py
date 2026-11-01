"""Text normalization for comparing transcripts (eval, seam de-duplication, phantom matching)."""

from __future__ import annotations

import re
import unicodedata

FILLERS = {"eh", "euh", "uh", "uhm", "um", "ehm", "hm", "hmm", "mm", "ah", "eum", "euhm"}

_UNITS = {
    "nl": {"nul": 0, "een": 1, "één": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6, "zeven": 7,
           "acht": 8, "negen": 9, "tien": 10, "elf": 11, "twaalf": 12, "dertien": 13, "veertien": 14,
           "vijftien": 15, "zestien": 16, "zeventien": 17, "achttien": 18, "negentien": 19},
    "en": {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19},
}
_TENS = {
    "nl": {"twintig": 20, "dertig": 30, "veertig": 40, "vijftig": 50, "zestig": 60, "zeventig": 70,
           "tachtig": 80, "negentig": 90},
    "en": {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
           "ninety": 90},
}
_NL_COMPOUND = re.compile(
    r"^(een|één|twee|drie|vier|vijf|zes|zeven|acht|negen)(?:en|ën)"
    r"(twintig|dertig|veertig|vijftig|zestig|zeventig|tachtig|negentig)$"
)


def number_value(word: str, lang: str) -> int | None:
    """Single-token number words 0–99 (incl. Dutch 'eenentwintig') → int."""
    units, tens = _UNITS.get(lang, {}), _TENS.get(lang, {})
    if word in units:
        return units[word]
    if word in tens:
        return tens[word]
    if lang == "nl" and (m := _NL_COMPOUND.match(word)):
        return units[m.group(1)] + tens[m.group(2)]
    return None


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_words(text: str, lang: str = "nl", drop_fillers: bool = True) -> list[str]:
    """Lowercase words without punctuation, fillers, [?…?] markers or accents; numbers as digits."""
    text = re.sub(r"\[\?(.*?)\?\]", r"\1", text)          # keep the words inside [?…?]
    text = text.lower().replace("’", "'")
    text = re.sub(r"(?<=\d)[.,](?=\d)", "", text)          # 1.000 / 1,000 → 1000 (cheap; good enough)
    text = re.sub(r"[-‐–—/]", " ", text)                   # IS-LM → is lm (on both sides)
    text = re.sub(r"[^\w\s']", " ", text)
    words = []
    for w in text.split():
        w = w.strip("'")
        if not w or (drop_fillers and w in FILLERS):
            continue
        value = number_value(w, lang)
        words.append(str(value) if value is not None else _strip_accents(w))
    # English "twenty one" (after hyphen split) → 21
    out: list[str] = []
    for w in words:
        if out and w.isdigit() and len(w) == 1 and out[-1].isdigit() and len(out[-1]) == 2 and out[-1].endswith("0"):
            out[-1] = str(int(out[-1]) + int(w))
        else:
            out.append(w)
    return out


def normalize_text(text: str, lang: str = "nl") -> str:
    return " ".join(normalize_words(text, lang))


def is_masked(text: str) -> bool:
    """Whisper's '***' output: no real words, or at least half of the tokens are asterisk runs."""
    tokens = text.split()
    if not tokens or "*" not in text:
        return False
    stars = sum(1 for t in tokens if t.strip(".,!?;:").strip("*") == "")
    return stars * 2 >= len(tokens)


def clean_tokens(text: str) -> list[str]:
    """Tokens that are real words (drops '***' and punctuation-only tokens)."""
    return [t for t in text.split() if "*" not in t and re.search(r"\w", t)]
