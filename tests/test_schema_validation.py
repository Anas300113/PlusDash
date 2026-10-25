from src.canonical.validators import validate_canonical_question


def _q(**kw):
    base = {"subject": "maths", "topic": "maths-arithmetic",
            "question_type": "mcq", "correct_answer": "B",
            "options_json": [{"letter": "A", "text": "1"},
                             {"letter": "B", "text": "2"}]}
    base.update(kw)
    return base


def test_valid_mcq_passes():
    assert validate_canonical_question(_q()).passed


def test_missing_fields_fail():
    r = validate_canonical_question({})
    assert not r.passed
    assert r.issues


def test_answer_must_be_among_options():
    r = validate_canonical_question(_q(correct_answer="Z"))
    assert not r.passed


def test_bad_difficulty_fails():
    r = validate_canonical_question(_q(difficulty=9))
    assert not r.passed


def test_unknown_subject_fails():
    r = validate_canonical_question(_q(subject="astrology"))
    assert not r.passed
