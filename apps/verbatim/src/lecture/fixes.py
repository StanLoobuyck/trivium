"""Fix misheard terms in the transcript (no LLM): the course's own fix list, then sound-alikes of slide terms.

Whisper writes "nent" for NAND even with NAND in its prompt. A word is replaced automatically only when
  - it sounds like a slide term: same consonant skeleton (vowels merged, d/t b/p v/f z/s c/k alike), and
  - it is rare in both Dutch and English (so "naar" never becomes NOR, nor "veel" VIL).
Tested on four lectures: nent/nend/NENT → NAND, ELU → ALU, boeliaanse → Booleaanse, no false hits.
Every replacement is counted and listed in the Quality check.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache
from typing import Any

FIX_VERSION = 2  # part of the stitch stage hash: bump when the rules change
RARE_ZIPF = 2.0
_WORD = re.compile(r"[^\W\d_]+")


def skeleton(word: str) -> str:
    """Rough sound key: nand, nent, nend → "nant"."""
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    w = re.sub(r"[^a-z]", "", w).replace("y", "i").replace("ph", "f").replace("ck", "k").replace("dt", "t")
    w = re.sub(r"[aeiou]+", "a", w).translate(str.maketrans("dbvzc", "tpfsk"))
    return re.sub(r"(.)\1+", r"\1", w)


@lru_cache(maxsize=20000)
def _rare(word: str) -> bool:
    from wordfreq import zipf_frequency

    return max(zipf_frequency(word, "nl"), zipf_frequency(word, "en")) < RARE_ZIPF


class Fixer:
    def __init__(self, terms: list[dict], corrections: dict[str, str]):
        self.counts: Counter[tuple[str, str, str]] = Counter()
        # longest first, so "nent poort" wins over "nent"
        self.course = [(re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE), wrong, right)
                       for wrong, right in sorted(corrections.items(), key=lambda kv: -len(kv[0]))
                       if wrong.strip() and right.strip()]
        self.known = {t["term"].lower() for t in terms} | {r.lower() for r in corrections.values()}
        self.sounds: dict[str, str] = {}
        for t in terms:
            term = t["term"]
            # one plain word of 3+ letters; names (the lecturer) are left to Whisper
            if t.get("source") != "lecturer" and len(term) >= 3 and _WORD.fullmatch(term):
                self.sounds.setdefault(skeleton(term), term)

    def _auto(self, m: re.Match) -> str:
        w = m.group(0)
        if len(w) < 3 or w.lower() in self.known:
            return w
        term = self.sounds.get(skeleton(w))
        if term is None or not _rare(w.lower()):
            return w
        if w[0].islower() and not term.isupper():
            term = term[0].lower() + term[1:]  # "Algebraïsche" opens a slide title; mid-sentence it's lowercase
        self.counts[("auto", w, term)] += 1
        return term

    def fix(self, text: str, count: bool = True) -> str:
        before = self.counts.copy()
        for pattern, wrong, right in self.course:
            text, n = pattern.subn(right, text)
            if n:
                self.counts[("course", wrong, right)] += n
        text = _WORD.sub(self._auto, text)
        if not count:
            self.counts = before
        return text

    def report(self) -> list[dict[str, Any]]:
        return [{"kind": kind, "from": wrong, "to": right, "count": n}
                for (kind, wrong, right), n in self.counts.most_common()]


def apply_fixes(segments: list[dict], terms: list[dict], corrections: dict[str, str]) -> list[dict[str, Any]]:
    """Fix segment texts in place (and their word lists, uncounted); returns what was replaced how often."""
    fixer = Fixer(terms, corrections)
    for seg in segments:
        seg["text"] = fixer.fix(seg["text"])
        for w in seg.get("words") or []:
            w["word"] = fixer.fix(w["word"], count=False)
    return fixer.report()
