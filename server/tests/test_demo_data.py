"""The demo's seeded usage is keyed by the sentence the reader sends, so the script's port
of web/lib/sentence.ts extractSentence must cut sentences the same way."""
from scripts.build_demo_data import extract_sentence

TEXT = "첫 문장이다. 둘째 문장인가? 셋째!\n넷째 줄"


def test_extract_sentence_matches_the_reader():
    assert extract_sentence(TEXT, 0) == "첫 문장이다."
    assert extract_sentence(TEXT, TEXT.index("둘째")) == "둘째 문장인가?"
    assert extract_sentence(TEXT, TEXT.index("셋째")) == "셋째!"
    assert extract_sentence(TEXT, TEXT.index("넷째")) == "넷째 줄"


def test_demo_data_has_every_sample_and_no_secrets():
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).parents[2] / "web" / "lib" / "demo-data.json").read_text("utf-8"))
    assert len(data["books"]) == 3 and set(data["texts"]) == {str(b["id"]) for b in data["books"]}
    assert all(t["lemma"] in data["translations"] for w in data["texts"].values() for t in w["tokens"])
    assert "API_KEY" not in json.dumps(data)
