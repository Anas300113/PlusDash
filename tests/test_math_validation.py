from src.canonical.math_verifier import verify_arithmetic, verify_sequence_next


def test_verify_addition():
    assert verify_arithmetic("What is 34 + 12?", "46") is True
    assert verify_arithmetic("What is 34 + 12?", "47") is False


def test_verify_unparseable_returns_none():
    assert verify_arithmetic("Explain photosynthesis", "plants") is None


def test_verify_arithmetic_sequence():
    assert verify_sequence_next([2.0, 5.0, 8.0], 11.0) is True
    assert verify_sequence_next([2.0, 5.0, 8.0], 12.0) is False


def test_verify_non_arithmetic_returns_none():
    assert verify_sequence_next([2.0, 4.0, 8.0], 16.0) is None
