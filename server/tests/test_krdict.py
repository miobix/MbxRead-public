"""Epic 21: krdict example-sentence extraction (search + view-fallback)."""
import httpx

from translate_svc import krdict

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<channel>
  <item>
    <target_code>12345</target_code>
    <word>기타</word>
    <pos>명사</pos>
    <origin>其他</origin>
    <sense>
      <definition>현악기의 하나.</definition>
      <translation>
        <trans_word>guitar</trans_word>
        <trans_dfn>a string instrument</trans_dfn>
      </translation>
    </sense>
  </item>
</channel>
"""

VIEW_XML = """<?xml version="1.0" encoding="UTF-8"?>
<channel>
  <item>
    <target_code>12345</target_code>
    <word_info>
      <word>기타</word>
      <sense_info>
        <definition>현악기의 하나.</definition>
        <example_info>
          <type>구</type>
          <example>기타를 치다</example>
        </example_info>
        <example_info>
          <type>문장</type>
          <example>그는 기타를 잘 친다.</example>
        </example_info>
      </sense_info>
    </word_info>
  </item>
</channel>
"""


class _Resp:
    def __init__(self, text):
        self.text = text


def _fake_get_factory(view_text=VIEW_XML):
    def fake_get(url, params=None, timeout=None):
        if url == krdict.VIEW_URL:
            return _Resp(view_text)
        return _Resp(SEARCH_XML)

    return fake_get


def test_lookup_attaches_examples_from_view(monkeypatch):
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "get", _fake_get_factory())

    entries = krdict.lookup("기타")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["word"] == "기타"
    assert entry["target_code"] == "12345"
    assert entry["origin"] == "其他"
    assert entry["definitions"][0]["en_word"] == "guitar"
    assert entry["examples"] == ["기타를 치다", "그는 기타를 잘 친다."]


def test_lookup_origin_defaults_empty_when_absent(monkeypatch):
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "test-key")
    no_origin_xml = SEARCH_XML.replace("<origin>其他</origin>", "")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, params=None, timeout=None: _Resp(no_origin_xml)
        if url == krdict.API_URL
        else _Resp(VIEW_XML),
    )

    entries = krdict.lookup("기타")
    assert entries[0]["origin"] == ""


def test_lookup_with_examples_false_skips_view_call(monkeypatch):
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "test-key")
    view_calls = []

    def fake_get(url, params=None, timeout=None):
        if url == krdict.VIEW_URL:
            view_calls.append(params)
            return _Resp(VIEW_XML)
        return _Resp(SEARCH_XML)

    monkeypatch.setattr(httpx, "get", fake_get)

    entries = krdict.lookup("기타", with_examples=False)
    assert entries[0]["examples"] == []
    assert view_calls == []  # no view API round-trip


def test_lookup_survives_view_failure(monkeypatch):
    """A broken/empty view response degrades to no examples, not an error."""
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "test-key")

    def fake_get(url, params=None, timeout=None):
        if url == krdict.VIEW_URL:
            return _Resp("<not-xml")  # unparseable
        return _Resp(SEARCH_XML)

    monkeypatch.setattr(httpx, "get", fake_get)

    entries = krdict.lookup("기타")
    assert entries[0]["examples"] == []


def test_lookup_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "")
    called = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: called.append(1))

    assert krdict.lookup("기타") == []
    assert called == []


def test_view_dedupes_and_caps_examples(monkeypatch):
    monkeypatch.setattr(krdict, "KRDICT_API_KEY", "test-key")
    many = "".join(
        f"<example_info><example>예문 {i}</example></example_info>" for i in range(10)
    )
    dup_view = (
        "<channel><item><word_info><sense_info>"
        "<example_info><example>같은 예문</example></example_info>"
        "<example_info><example>같은 예문</example></example_info>"
        f"{many}"
        "</sense_info></word_info></item></channel>"
    )
    monkeypatch.setattr(httpx, "get", _fake_get_factory(view_text=dup_view))

    examples = krdict.lookup("기타")[0]["examples"]
    assert examples[0] == "같은 예문"
    assert examples.count("같은 예문") == 1  # deduped
    assert len(examples) == 5  # capped at max_examples
