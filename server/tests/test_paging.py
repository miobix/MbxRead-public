from server.paging import split_pages


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
