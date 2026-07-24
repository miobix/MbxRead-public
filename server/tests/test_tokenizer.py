import pytest

from server.tokenizer import tokenize

# (input eojeol, expected lemma)
CONJUGATION_CASES = [
    ("입고", "입다"),
    ("입었어요", "입다"),
    ("했어요", "하다"),
    ("공부했어요", "공부하다"),
    ("학교에", "학교"),
    ("갔다", "가다"),
    ("예뻐요", "예쁘다"),
    ("사람들이", "사람"),
    ("학생이에요", "학생"),
]


# A word wrapped in brackets/quotes (or trailed by punctuation) must still yield a
# token — a leading symbol morpheme used to swallow the whole eojeol, so clicking it
# opened nothing and a saved term never highlighted. The stripped surface covers just
# the word, not the surrounding punctuation.
LEADING_SYMBOL_CASES = [
    ("〈자연계의", "자연계", "자연계의"),
    ("<자연계의", "자연계", "자연계의"),
    ('"학교에', "학교", "학교에"),
    ("(사람들이)", "사람", "사람들이"),
    ("…진짜", "진짜", "진짜"),
    ("좋았다!", "좋다", "좋았다"),
]

# Noun-derivational suffixes (XSN) glue onto the head noun as one compound lemma,
# except the plural 들 which stays dropped (사람들이 -> 사람).
COMPOUND_NOUN_CASES = [
    ("자연계의", "자연계"),
    ("가능성", "가능성"),
    ("사람들이", "사람"),
]


@pytest.mark.parametrize("text,expected_lemma", CONJUGATION_CASES)
def test_conjugation_lemma(text, expected_lemma):
    tokens = tokenize(text)
    lemmas = [t.lemma for t in tokens]
    assert expected_lemma in lemmas, f"{text!r} -> {lemmas}, expected {expected_lemma!r}"


@pytest.mark.parametrize("text,expected_lemma", COMPOUND_NOUN_CASES)
def test_compound_noun_lemma(text, expected_lemma):
    lemmas = [t.lemma for t in tokenize(text)]
    assert lemmas == [expected_lemma], f"{text!r} -> {lemmas}, expected [{expected_lemma!r}]"


@pytest.mark.parametrize("text,expected_lemma,expected_surface", LEADING_SYMBOL_CASES)
def test_leading_symbol_yields_token(text, expected_lemma, expected_surface):
    tokens = tokenize(text)
    assert len(tokens) == 1, f"{text!r} -> {[t.surface for t in tokens]}"
    tok = tokens[0]
    assert tok.lemma == expected_lemma, f"{text!r} -> {tok.lemma!r}"
    assert tok.surface == expected_surface, f"{text!r} -> {tok.surface!r}"
    assert text[tok.s : tok.e] == tok.surface


@pytest.mark.parametrize("text,_", CONJUGATION_CASES)
def test_offsets_round_trip(text, _):
    tokens = tokenize(text)
    for t in tokens:
        assert text[t.s : t.e] == t.surface


def test_multi_sentence_text_offsets_round_trip():
    text = "그는 옷을 입고 나갔다. 날씨가 좋아서 기분이 좋았다! 학교에 가야 할까?"
    tokens = tokenize(text)
    assert tokens
    for t in tokens:
        assert text[t.s : t.e] == t.surface
    lemmas = {t.lemma for t in tokens}
    assert "입다" in lemmas
    assert "학교" in lemmas


def test_mixed_latin_digits_punctuation_does_not_crash():
    text = "hello world 123, 오늘은 2026년 7월 21일이에요! ㅋㅋㅋ 진짜 좋아요~~"
    tokens = tokenize(text)
    for t in tokens:
        assert text[t.s : t.e] == t.surface


def test_particle_only_text_does_not_crash():
    text = "을 를 는 이 가"
    tokens = tokenize(text)
    for t in tokens:
        assert text[t.s : t.e] == t.surface


def test_empty_string_returns_no_tokens():
    assert tokenize("") == []


def test_whitespace_only_returns_no_tokens():
    assert tokenize("   \n\t  ") == []
