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
    "<SYNC Start=4000><P Class=KRCC>아직이요.<br>배고파요.\n"
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
    '    <p begin="00:00:04.000" end="00:00:08.000">글쎄요,<br/>잘 모르겠어요.</p>\n'
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


def test_srt_strips_substation_tags_left_by_a_converter():
    """A real .srt off a converter carries {\\an8} position tags and \\N breaks —
    SubStation markup that survived the conversion. The stripping lives in the
    shared cleanup for exactly this reason, so it can't be an .ass-only concern.
    """
    converted = (
        "1\n00:00:01,000 --> 00:00:03,000\n{\\an8}\"말포이 저택\"\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n{\\an8}{\\pos(190,270)}첫\\N화\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\n{y:i}기울임꼴 자막\n\n"
    )
    text, _ = extract(converted.encode("utf-8"), "ep.srt")
    assert text.splitlines() == ['"말포이 저택"', "첫 화", "기울임꼴 자막"]


def test_a_brace_in_real_dialogue_is_left_alone():
    """Only markup braces go — an override block always opens with a backslash."""
    braced = "1\n00:00:01,000 --> 00:00:03,000\n{중요} 표시가 뭐예요?\n\n"
    text, _ = extract(braced.encode("utf-8"), "ep.srt")
    assert text.splitlines() == ["{중요} 표시가 뭐예요?"]


def test_two_speakers_in_one_cue_stay_on_separate_lines():
    """The dash convention is the only speaker signal a plain track carries, so
    it survives as a line break where ordinary display wrapping does not — the
    second cue here is one person's sentence wrapped across two lines, the first
    is two people.
    """
    two_handed = (
        "1\n00:00:01,000 --> 00:00:03,000\n- 안녕하세요\n- 반가워요, 찰리\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n오늘은 정말\n좋은 날씨네요\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\n- 어제 그 얘기\n들었어요?\n- 아직요\n\n"
    )
    text, _ = extract(two_handed.encode("utf-8"), "ep.srt")
    assert text.splitlines() == [
        "- 안녕하세요",
        "- 반가워요, 찰리",
        "오늘은 정말 좋은 날씨네요",
        "- 어제 그 얘기 들었어요?",  # wrapped continuation rejoins its own turn
        "- 아직요",
    ]


def test_a_leading_minus_number_is_not_a_speaker_change():
    """Dash + digit is a number, not a turn — it stays joined to the line above."""
    cold = "1\n00:00:01,000 --> 00:00:03,000\n오늘 최저 기온은\n-5도입니다\n\n"
    text, _ = extract(cold.encode("utf-8"), "ep.srt")
    assert text.splitlines() == ["오늘 최저 기온은 -5도입니다"]


def test_a_long_silence_becomes_a_paragraph_break():
    """The timings are the only structure a subtitle file has. Inside a
    conversation cues follow within a tenth of a second, so a multi-second hole
    is a scene change — and the reader renders the blank line as a paragraph.
    """
    scened = (
        "1\n00:00:01,000 --> 00:00:03,000\n어디 가세요?\n\n"
        "2\n00:00:03,100 --> 00:00:05,000\n집에요\n\n"
        "3\n00:00:12,000 --> 00:00:14,000\n다음 날 아침\n\n"
    )
    text, _ = extract(scened.encode("utf-8"), "ep.srt")
    assert text.splitlines() == ["어디 가세요?", "집에요", "", "다음 날 아침"]


def test_a_sami_clear_cue_counts_as_silence():
    """SAMI can't leave a hole in its timeline — every cue runs up against the
    next — so its silence arrives as a text-less clear cue instead. Measuring the
    gap from the last cue that *spoke* covers both shapes with one rule.
    """
    quiet = (
        "<SAMI><BODY>\n"
        "<SYNC Start=1000><P Class=KRCC>먼저 갈게요\n"
        "<SYNC Start=3000><P Class=KRCC>&nbsp;\n"
        "<SYNC Start=9000><P Class=KRCC>어, 잠깐만\n"
        "<SYNC Start=11000><P Class=KRCC>&nbsp;\n"
        "</BODY></SAMI>\n"
    )
    text, _ = extract(quiet.encode("cp949"), "ep.smi")
    assert text.splitlines() == ["먼저 갈게요", "", "어, 잠깐만"]


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
