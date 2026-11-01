"""Deterministic term list from slide text (no LLM) and the Whisper prompt built from it.

Candidates are words Whisper is likely to mishear in a lecture: acronyms (NAND, ALU), words with digits
(74LS00), English words on Dutch slides (carry, enable) and words that are rare in the lecture language
(Karnaugh, minterm). Ranked by how many slides use them × how likely they are misheard.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

from .config import Config, Course

WHISPER_PROMPT_MAX_TOKENS = 223  # faster-whisper keeps the last n_text_ctx // 2 - 1 tokens; Groq allows 224

_TOKEN = re.compile(r"(?:\d+[^\W\d_]|[^\W\d_])[\w’'-]*", re.UNICODE)  # keeps a trailing "-" (fragments)
_URL = re.compile(r"\S+@\S+|https?://\S+|www\.\S+")  # e-mail addresses and links are not spoken terms
_OTHER_LANG = {"nl": "en", "en": "nl"}
# Rare words formed with these endings are regular Dutch/English that Whisper spells fine on its own
_REGULAR_ENDINGS = {
    "nl": ("ingen", "ing", "ende", "bare", "baar", "iteit", "ische", "isch", "aties", "atie", "eren", "heid"),
    "en": ("ations", "ation", "ing", "ness", "ity", "able", "ible", "ically"),
}
_VARIABLES = set("ABCDWXYZ")  # products of variables (AB, XY) are not terms; add e.g. BCD via extra_terms
_SENTENCE = {
    "nl": ("Dit is een les {course}", " over {terms}.", "."),
    "en": ("This is a lecture {course}", " on {terms}.", "."),
}
_BY = {"nl": " door {name}", "en": " by {name}"}
_COURSE = {"nl": "van {name}", "en": "of {name}"}


def _zipf(word: str, lang: str) -> float:
    from wordfreq import zipf_frequency

    return zipf_frequency(word, lang)


def classify(word: str, language: str, rare_zipf: float) -> float:
    """Weight for how likely Whisper mishears this word (0 = not a term)."""
    letters = [c for c in word if c.isalpha()]
    if len(letters) < 2 or not all(unicodedata.name(c, "").startswith("LATIN") for c in letters):
        return 0.0  # formula symbols: PDFs write maths in italic Unicode letters and borrowed overbars
    if any(c in "’'" for c in word) and not word.islower():
        return 0.0  # X’Y: complemented variables
    if "-" in word and any(c.isdigit() for c in word):
        return 0.0  # codes like B-KUL-H01L1A (course codes on the title slide)
    if sum(c.isupper() for c in letters) >= 2 and sum(c.isupper() for c in letters) >= 0.6 * len(letters):
        if set(letters) <= _VARIABLES:
            return 0.0
        common = max(_zipf(word.lower(), language), _zipf(word.lower(), _OTHER_LANG[language]))
        if len(word) >= 4 and word.isalpha() and common >= rare_zipf:
            return 0.0  # an ordinary word in capitals for emphasis: DUUR, HERHALING
        return 2.0  # acronym: NAND, ALU, SOP, CMOS
    if any(c.isdigit() for c in word):
        if len(word) < 4 or classify("".join(letters), language, rare_zipf) == 0.0 and not word[0].isdigit():
            return 0.0  # variables like x1, c0; "Les3" is an ordinary word with a number
        return 1.5  # 74LS00, ALUControl1
    if len(word) < 4:
        return 0.0
    own = _zipf(word.lower(), language)
    other = _zipf(word.lower(), _OTHER_LANG[language])
    if own >= rare_zipf and other - own < 1.5:
        return 0.0  # ordinary word of the lecture language
    if other - own >= 1.5:
        return 1.5  # word from the other language (English on Dutch slides)
    if word.lower().endswith(_REGULAR_ENDINGS[language]):
        return 0.4  # rare but regularly formed: implementeerbare, schakelingen
    return 1.0  # rare word: jargon, names (Karnaugh, Booleaanse, minterm)


def build_term_list(slide_texts: list[str], extra_lines: list[str], course: Course, conf: Config) -> list[dict]:
    """Ranked terms: course extra_terms and lecturer first, then candidates from the slides.

    slide_texts: one text per slide (counts per slide); extra_lines: boilerplate (sidebar) lines, counted once.
    """
    tc = conf.terms
    slides_with: Counter[str] = Counter()
    forms: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for text in [*slide_texts, "\n".join(extra_lines)]:
        seen = set()
        for tok in _TOKEN.findall(_URL.sub(" ", _dehyphenate(text))):
            if tok.endswith("-"):
                continue  # word broken over two lines that couldn't be joined ("Combina-")
            tok = tok.strip("’'-")
            key = tok.lower()
            forms[key][tok] += 1
            seen.add(key)
        slides_with.update(seen)
    terms = []
    for key, n in slides_with.items():
        form = _preferred_form(forms[key])
        w = classify(form, course.language, tc.rare_zipf)
        if w > 0:
            terms.append({"term": form, "slides": n, "weight": w, "score": round(w * n, 2), "source": "slides"})
    terms.sort(key=lambda t: (-t["score"], t["term"].lower()))
    fixed = [{"term": t, "source": "course"} for t in course.extra_terms]
    if course.lecturer:
        fixed.append({"term": course.lecturer, "source": "lecturer"})
    known = {t["term"].lower() for t in fixed}
    return fixed + [t for t in terms if t["term"].lower() not in known][: max(0, tc.max_terms - len(fixed))]


def _dehyphenate(text: str) -> str:
    """Join words hyphenated over a line break: "Combina-\ntorisch" → "Combinatorisch"."""
    return re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)


def _preferred_form(forms: Counter[str]) -> str:
    """Most common spelling; on a tie prefer the one with capitals (NAND over nand)."""
    return max(forms.items(), key=lambda kv: (kv[1], sum(c.isupper() for c in kv[0])))[0]


@lru_cache(maxsize=1)
def _whisper_tokenizer():
    """The large-v3 tokenizer from the Hugging Face cache (Groq uses the same vocabulary); None if absent."""
    try:
        from huggingface_hub import try_to_load_from_cache
        from tokenizers import Tokenizer

        path = try_to_load_from_cache("Systran/faster-whisper-large-v3", "tokenizer.json")
        return Tokenizer.from_file(path) if isinstance(path, str) else None
    except Exception:  # noqa: BLE001 — optional: fall back to an estimate
        return None


def count_tokens(text: str) -> int:
    tok = _whisper_tokenizer()
    if tok is not None:
        return len(tok.encode(" " + text, add_special_tokens=False).ids)
    return int(len(text) / 2.5) + 1  # conservative: Dutch averages ~3.5 characters per token


def build_whisper_prompt(terms: list[dict], course: Course, max_tokens: int) -> str:
    """Short natural sentence in the lecture language naming the top terms, within max_tokens."""
    start, with_terms, end = _SENTENCE[course.language]
    head = start.format(course=_COURSE[course.language].format(name=course.name))
    lecturer = next((t["term"] for t in terms if t.get("source") == "lecturer"), None)
    if lecturer:
        head += _BY[course.language].format(name=lecturer)
    names = [t["term"] for t in terms if t.get("source") != "lecturer"]
    best = head + end
    lo, hi = 0, len(names)
    while lo < hi:  # longest prefix of the ranked terms that fits
        mid = (lo + hi + 1) // 2
        sentence = head + with_terms.format(terms=", ".join(names[:mid]))
        if count_tokens(sentence) <= max_tokens:
            lo, best = mid, sentence
        else:
            hi = mid - 1
    return best if count_tokens(best) <= max_tokens else ""


def combine_prompt(term_prompt: str, previous_tail: str, max_tokens: int = WHISPER_PROMPT_MAX_TOKENS) -> str:
    """Term sentence first, then the previous chunk's tail, trimmed from its start so the total fits.

    Whisper keeps the *end* of an over-long prompt, so without trimming the terms would be cut off.
    """
    if not term_prompt:
        return previous_tail
    words = previous_tail.split()
    while words and count_tokens(f"{term_prompt} {' '.join(words)}") > max_tokens:
        words = words[max(1, len(words) // 8):]
    return f"{term_prompt} {' '.join(words)}".strip()
