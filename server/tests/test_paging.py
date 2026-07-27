from server.paging import snap_back, snap_forward, split_pages


def test_empty_text_returns_one_empty_page():
    assert split_pages("") == [""]


def test_join_reconstructs_original_text():
    text = "문장입니다. " * 300
    pages = split_pages(text, max_chars=100)
    assert "".join(pages) == text


def test_pages_respect_max_chars_when_a_break_point_exists():
    text = "문장입니다. " * 300
    pages = split_pages(text, max_chars=100)
    assert len(pages) > 1
    for page in pages[:-1]:
        assert len(page) <= 100


def test_never_splits_mid_sentence():
    text = "첫 번째 문장입니다. 두 번째 문장이에요! 세 번째 문장인가요? 마지막 문장입니다."
    pages = split_pages(text, max_chars=20)
    assert "".join(pages) == text
    for page in pages[:-1]:
        assert page and (page[-1] in ".!?…" or page.endswith("\n"))


def test_breaks_at_newlines_too():
    text = "첫 줄\n둘째 줄\n셋째 줄"
    pages = split_pages(text, max_chars=6)
    assert "".join(pages) == text
    for page in pages[:-1]:
        assert page.endswith("\n")


def test_single_long_sentence_with_no_break_point_is_not_split():
    text = "가" * 2000
    pages = split_pages(text)
    assert "".join(pages) == text
    assert len(pages) == 1


# --- snap_back / snap_forward (Epic 24 text windows) ------------------------

TEXT = "첫째 문장이다. 둘째 문장이다.\n셋째 문장이다."


def test_snap_back_returns_boundary_at_or_before_index():
    # index inside the second sentence snaps back to just after the first's period —
    # i.e. onto the space, not onto the first character of the next sentence
    i = TEXT.index("둘째") + 2
    assert snap_back(TEXT, i) == TEXT.index(".") + 1


def test_snap_back_before_any_boundary_returns_zero():
    assert snap_back(TEXT, 3) == 0


def test_snap_forward_returns_boundary_at_or_after_index():
    i = TEXT.index("둘째") + 2
    # next boundary is the second sentence's period (which ends before the newline)
    assert snap_forward(TEXT, i) == TEXT.index("\n")


def test_snap_forward_past_last_boundary_returns_length():
    assert snap_forward(TEXT, len(TEXT) - 1) == len(TEXT)
    assert snap_forward(TEXT, len(TEXT) + 50) == len(TEXT)


def test_snaps_clamp_out_of_range_indices():
    assert snap_back(TEXT, -10) == 0
    assert snap_back(TEXT, len(TEXT) + 10) <= len(TEXT)


def test_snapped_window_never_starts_or_ends_mid_sentence():
    text = "문장입니다. " * 200
    start = snap_back(text, 137)
    end = snap_forward(text, start + 500)
    window = text[start:end]
    # every window boundary lands right after a sentence-ending period
    assert start == 0 or text[start - 1] in " ."
    assert window.rstrip().endswith(".")
