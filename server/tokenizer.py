"""kiwipiepy wrapper: text -> eojeol tokens with a heuristic dictionary-form lemma.

Eojeols are runs of non-whitespace in the original text. Each eojeol's morphemes
(from kiwi.tokenize) are inspected to pick a single "primary" morpheme, which
determines the emitted lemma. See docs/ARCHITECTURE.md / SPEC.md section 6 for the
rule order. Wrong guesses are expected and acceptable — the UI lets the user correct
the lemma before saving; a crash or a missing offset is the only real bug.
"""
import re
from dataclasses import dataclass

from kiwipiepy import Kiwi

_kiwi = Kiwi()

_HADA_NOUN_TAGS = {"NNG", "NNP", "XR"}
_HADA_SUFFIX_TAGS = {"XSV", "XSA"}
_VERB_PREFIXES = ("VV", "VA", "VX")
_STANDALONE_TAGS = {"NNG", "NNP", "NNB", "NR", "NP", "MAG", "MAJ", "IC"}
_NOUN_TAGS = {"NNG", "NNP", "NNB", "NR", "NP"}

# Symbol tags stripped off an eojeol's ends (SSO/SSC are newer kiwi's split of SS).
_SYMBOL_TAGS = {"SF", "SP", "SS", "SSO", "SSC", "SE", "SO", "SW"}

# Plural 들 is inflection, not a new word (사람들 → 사람); other XSN suffixes form a
# compound lemma (자연계의 → 자연계).
_XSN_NOT_MERGED = {"들"}

_EOJEOL_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class Token:
    surface: str
    s: int
    e: int
    lemma: str
    pos: str


def tokenize(text: str) -> list[Token]:
    morphs = _kiwi.tokenize(text)
    tokens: list[Token] = []

    morph_idx = 0
    n_morphs = len(morphs)

    for eojeol in _EOJEOL_RE.finditer(text):
        estart, eend = eojeol.start(), eojeol.end()

        while morph_idx < n_morphs and morphs[morph_idx].start < estart:
            morph_idx += 1
        eo_morphs = []
        while morph_idx < n_morphs and morphs[morph_idx].start < eend:
            eo_morphs.append(morphs[morph_idx])
            morph_idx += 1

        if not eo_morphs:
            continue

        # Otherwise a leading 〈 or " becomes the first morpheme and the word gets no
        # token at all. Internal symbols (이야기?라고) stay.
        lo, hi = 0, len(eo_morphs)
        while lo < hi and eo_morphs[lo].tag in _SYMBOL_TAGS:
            lo += 1
        while hi > lo and eo_morphs[hi - 1].tag in _SYMBOL_TAGS:
            hi -= 1
        core = eo_morphs[lo:hi]
        if not core:
            continue

        lemma, pos = _resolve_lemma(core)
        if lemma is None:
            continue

        cstart, cend = core[0].start, core[-1].end
        tokens.append(
            Token(surface=text[cstart:cend], s=cstart, e=cend, lemma=lemma, pos=pos)
        )

    return tokens


def _resolve_lemma(eo_morphs: list) -> tuple[str | None, str | None]:
    first = eo_morphs[0]
    second = eo_morphs[1] if len(eo_morphs) > 1 else None

    # Rule 1: hada-derivation (공부했어요 -> 공부하다)
    if first.tag in _HADA_NOUN_TAGS and second is not None and second.tag in _HADA_SUFFIX_TAGS:
        pos = "VV" if second.tag == "XSV" else "VA"
        return first.form + "하다", pos

    # Rule 2: verb/adjective stem (입고 -> 입다, 갔다 -> 가다, 예뻐요 -> 예쁘다)
    if first.tag.startswith(_VERB_PREFIXES):
        return first.form + "다", first.tag

    # Rule 3: bare noun/adverb/etc (학교에 -> 학교); a noun absorbs XSN suffixes (자연계의 -> 자연계)
    if first.tag in _STANDALONE_TAGS:
        lemma = first.form
        if first.tag in _NOUN_TAGS:
            for m in eo_morphs[1:]:
                if m.tag == "XSN" and m.form not in _XSN_NOT_MERGED:
                    lemma += m.form
                else:
                    break
        return lemma, first.tag

    # Rule 4: eojeol is only particles/endings/symbols/numbers -> no token
    return None, None
