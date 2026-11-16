import pytest

from scripts.eval_usage import SENSES, parse_explanation, score_picks, sense_matches


@pytest.mark.parametrize(
    "line, expected",
    [
        ("ride (to ride/take transport). Same sense: 3, 4, 5.", ("ride", {3, 4, 5})),
        ("Take time (needs (some) time). Same sense: 1", ("take time", {1})),
        ("cold (temperature is low). Same sense: none.", ("cold", set())),
        ("cold (low). same sense: 2 and 4", None),
        ("Sense: ride\nExamples: 1", None),
    ],
)
def test_parse_explanation(line, expected):
    assert parse_explanation(line) == expected


def test_sense_matches_label_with_underscore_or_longer_phrase():
    assert sense_matches("take time", "take_time")
    assert sense_matches("ride a vehicle", "ride")
    assert not sense_matches("rider", "ride")


def test_score_picks():
    # examples 1,2 same sense; 3 not; model picked 1 and 3
    assert score_picks({1, 3}, [True, True, False]) == (1, 1, 1, 0)
    assert score_picks(set(), [False, False]) == (0, 0, 0, 2)


def test_every_label_has_a_sense_entry():
    import csv
    from scripts.eval_usage import TSV

    rows = csv.DictReader(open(TSV, encoding="utf-8"), delimiter="\t")
    for r in rows:
        names = [s.split(":")[0] for s in SENSES[r["lemma"]]]
        assert any(sense_matches(n, r["sense"]) for n in names), r
