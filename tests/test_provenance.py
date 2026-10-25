from src.source.adapters.prep_adapter import PrepAdapter
from src.source.adapters.tutor_adapter import TutorAdapter


def test_tutor_adapter():
    out = TutorAdapter().to_canonical({
        "id": "q1", "subject": "mathematics", "topic": "arithmetic",
        "format": "multiple_choice", "difficulty": 2,
        "question_text": "2+2?", "options": ["3", "4"],
        "correct_answer": "4", "correct_index": 1,
        "worked_solution": "2+2=4"})
    assert out["subject"] == "maths"
    assert out["question_type"] == "mcq"
    assert out["correct_answer"] == "B"
    assert out["source_question_id"] == "q1"


def test_prep_adapter():
    out = PrepAdapter().to_canonical({
        "id": "maths-001", "subject": "maths", "topic": "arithmetic",
        "difficulty": 1, "type": "mcq", "question": "34 x 12?",
        "options": ["A) 368", "B) 408"], "answer": "B",
        "explanation": "ok", "region": "kent", "examBoard": "GL"})
    assert out["subject"] == "maths"
    assert out["correct_answer"] == "B"
    assert out["exam_board"] == "GL"
    assert out["region"] == "kent"


def test_adapters_never_leak_external_schema():
    for adapter, ext in [
        (TutorAdapter(), {"id": "1", "subject": "mathematics",
                          "question_text": "x", "options": ["a", "b"],
                          "correct_answer": "a", "correct_index": 0}),
        (PrepAdapter(), {"id": "2", "subject": "maths", "topic": "t",
                         "question": "x", "options": ["A) a", "B) b"],
                         "answer": "A", "explanation": "e"}),
    ]:
        out = adapter.to_canonical(ext)
        assert "question" not in out  # external key must not leak
        assert "subject" in out and "question_type" in out
