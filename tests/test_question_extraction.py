from src.pipeline.detect import split_candidates


def test_split_numbered_questions():
    text = "1. What is 2+2?\nA) 3 B) 4\n2. What is 3+3?\nA) 5 B) 6"
    out = split_candidates(text)
    assert [n for n, _ in out] == ["1", "2"]


def test_short_fragments_ignored():
    assert split_candidates("1. \n2. ok this is long enough body") != []
