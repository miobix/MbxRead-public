from server.paging import estimate_rows, split_pages, split_pages_by_rows


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


# --- split_pages_by_rows / estimate_rows -----------------------------------


def test_estimate_rows_counts_newlines_and_wraps_long_lines():
    assert estimate_rows("short line", chars_per_row=30) == 1
    assert estimate_rows("line one\nline two", chars_per_row=30) == 2
    assert estimate_rows("", chars_per_row=30) == 1
    assert estimate_rows("x" * 61, chars_per_row=30) == 3  # ceil(61/30)


def test_newline_dense_text_gets_more_pages_than_char_count_alone_would_predict():
    # A page of many short lines racks up estimated rows fast even though its raw
    # char count is small — this is exactly the case that motivated row-based
    # pagination over the old char-budget split.
    dense = "\n".join(["짧은 줄"] * 100)  # ~100 rows, ~500 chars
    pages = split_pages_by_rows(dense, max_rows=10, chars_per_row=30)
    assert "".join(pages) == dense
    assert len(pages) > 5
    for page in pages[:-1]:
        assert estimate_rows(page, chars_per_row=30) <= 10


def test_join_reconstructs_original_text_by_rows():
    text = "문장입니다. " * 300
    pages = split_pages_by_rows(text, max_rows=5, chars_per_row=20)
    assert "".join(pages) == text
    assert len(pages) > 1


def test_never_splits_mid_sentence_by_rows():
    text = "첫 번째 문장입니다. 두 번째 문장이에요! 세 번째 문장인가요? 마지막 문장입니다."
    pages = split_pages_by_rows(text, max_rows=1, chars_per_row=10)
    assert "".join(pages) == text
    for page in pages[:-1]:
        assert page and (page[-1] in ".!?…" or page.endswith("\n"))


def test_single_long_line_with_no_break_point_is_not_split_by_rows():
    text = "가" * 2000
    pages = split_pages_by_rows(text, max_rows=5, chars_per_row=30)
    assert "".join(pages) == text
    assert len(pages) == 1


def test_empty_text_returns_one_empty_page_by_rows():
    assert split_pages_by_rows("") == [""]
