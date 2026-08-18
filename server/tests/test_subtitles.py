"""Parser-level tests for import_tools/subtitles.py.

Each format gets a fixture written the way real files in that format actually
look — index lines and CRLF in the SRT, cue settings in the VTT, a CP949-encoded
SAMI, override tags in the ASS, tick-based times in the TTML — because the
parsers exist precisely to absorb those quirks.
"""

import pytest

from import_tools.subtitles import (
    SubtitleError,
    clean_title,
    decode,
    detect_format,
    extract,
)

SRT = (
    "1\r\n"
    "00:00:01,000 --> 00:00:03,500\r\n"
    "안녕하세요, 여러분.\r\n"
    "\r\n"
    "2\r\n"
    "00:00:04,000 --> 00:00:07,250\r\n"
    "오늘은 <i>정말</i> 좋은\r\n"
    "날씨네요.\r\n"
    "\r\n"
    "3\r\n"
    "00:01:02,000 --> 00:01:05,000\r\n"
    "♪\r\n"
    "\r\n"
)

VTT = (
    "WEBVTT\n"
    "Kind: captions\n"
    "Language: ko\n"
    "\n"
    "cue-1\n"
    "00:00:02.000 --> 00:00:05.000 line:85% align:center\n"
    "커피 한 잔 마실래요?\n"
    "\n"
    "00:00:06.000 --> 00:00:09.000\n"
    "네, 좋아요.\n"
)

SMI = (
    "<SAMI>\n"
    "<BODY>\n"
    "<SYNC Start=1000><P Class=KRCC>밥 먹었어요?\n"
    "<SYNC Start=3000><P Class=KRCC>&nbsp;\n"
    "<SYNC Start=5000><P Class=KRCC>아직이요.<br>배고파요.\n"
    "<SYNC Start=8000><P Class=KRCC>&nbsp;\n"
    "</BODY>\n"
    "</SAMI>\n"
)

ASS = (
    "[Script Info]\n"
    "Title: test\n"
    "\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\pos(190,270)}저기요, 잠깐만요.\n"
    "Dialogue: 0,0:00:05.00,0:00:08.50,Default,,0,0,0,,왜\\N그러세요?\n"
)

TTML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<tt xmlns="http://www.w3.org/ns/ttml" ttp:tickRate="10000000"\n'
    '    xmlns:ttp="http://www.w3.org/ns/ttml#parameter">\n'
    "  <body><div>\n"
    '    <p begin="10000000t" end="30000000t">이건 무슨 뜻이에요?</p>\n'
    '    <p begin="00:00:05.000" end="00:00:08.000">글쎄요,<br/>잘 모르겠어요.</p>\n'
    "  </div></body>\n"
    "</tt>\n"
)


def test_srt_joins_wrapped_lines_and_drops_markup():
    text, duration = extract(SRT.encode("utf-8"), "ep.srt")
    # A cue's own line break is display wrapping, so it folds into one line;
    # the music-only cue is dropped, but still counts toward the duration.
    assert text.splitlines() == ["안녕하세요, 여러분.", "오늘은 정말 좋은 날씨네요."]
    assert duration == 65


def test_vtt_ignores_header_cue_id_and_cue_settings():
    text, duration = extract(VTT.encode("utf-8"), "ep.vtt")
    assert text.splitlines() == ["커피 한 잔 마실래요?", "네, 좋아요."]
    assert duration == 9


def test_smi_reads_cp949_and_drops_clear_cues():
    """The Korean legacy encoding is the whole reason `decode` sniffs CP949 —
    a .smi that decoded as latin-1 would import as mojibake, not fail loudly."""
    text, duration = extract(SMI.encode("cp949"), "ep.smi")
    assert text.splitlines() == ["밥 먹었어요?", "아직이요. 배고파요."]
    assert duration == 8


def test_ass_strips_override_tags_and_hard_breaks():
    text, duration = extract(ASS.encode("utf-8"), "ep.ass")
    assert text.splitlines() == ["저기요, 잠깐만요.", "왜 그러세요?"]
    assert duration == 9  # 8.5s rounds to 9


def test_ttml_handles_tick_times_and_namespaces():
    text, duration = extract(TTML.encode("utf-8"), "ep.ttml")
    assert text.splitlines() == ["이건 무슨 뜻이에요?", "글쎄요, 잘 모르겠어요."]
    assert duration == 8


def test_rolling_duplicate_lines_collapse():
    rolling = (
        "1\n00:00:01,000 --> 00:00:02,000\n같은 줄\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\n같은 줄\n\n"
        "3\n00:00:03,000 --> 00:00:04,000\n다른 줄\n\n"
    )
    text, _ = extract(rolling.encode("utf-8"), "ep.srt")
    assert text.splitlines() == ["같은 줄", "다른 줄"]


def test_content_sniffing_beats_a_wrong_extension():
    """Misnamed subtitle files are common; the content is the authority."""
    assert detect_format(VTT, "actually-vtt.srt") == "vtt"
    assert detect_format(SMI, "mystery.txt") == "smi"
    assert detect_format(TTML, "netflix.xml") == "ttml"


def test_unrecognised_file_raises():
    with pytest.raises(SubtitleError):
        extract(b"just some prose, no timings at all", "notes.doc")


def test_empty_subtitle_file_raises():
    with pytest.raises(SubtitleError):
        extract(b"WEBVTT\n\n", "empty.vtt")


def test_malformed_ttml_raises_subtitle_error():
    with pytest.raises(SubtitleError):
        extract(b'<?xml version="1.0"?><tt><body><p>unclosed', "broken.ttml")


def test_decode_prefers_utf8_then_cp949():
    assert decode("한글".encode("utf-8")) == "한글"
    assert decode("한글".encode("cp949")) == "한글"


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("BoJack Horseman S01E01.ko.srt", "BoJack Horseman S01E01"),
        ("BoJack.Horseman.S01E02.korean.srt", "BoJack.Horseman.S01E02"),
        ("episode_03_ko-KR.vtt", "episode 03"),
        ("no_language_tag.srt", "no language tag"),
        ("", "untitled"),
    ],
)
def test_clean_title_strips_the_language_tag(filename, expected):
    """Every subtitle file carries a language tag; unstripped it would land in
    the title of every single imported episode."""
    assert clean_title(filename) == expected
