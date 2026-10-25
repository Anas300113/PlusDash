"""Deterministic maths verification. AI is never the final authority
where a computation suffices."""
from __future__ import annotations

import re
from fractions import Fraction


def _num(s: str) -> float | None:
    try:
        s = s.replace(",", "").strip().replace("£", "")
        if "/" in s and " " not in s:
            return float(Fraction(s))
        return float(s)
    except Exception:
        return None


def verify_arithmetic(question_text: str, expected: str) -> bool | None:
    """Try to verify simple arithmetic of the form 'a OP b' in the text.
    Returns True/False when computable, else None (needs human/AI review)."""
    m = re.search(r"(\d[\d,]*)\s*([+\-×x*÷/])\s*(\d[\d,]*)", question_text)
    if not m:
        return None
    a = _num(m.group(1))
    b = _num(m.group(3))
    op = m.group(2)
    if a is None or b is None:
        return None
    if op in ("+",):
        result = a + b
    elif op == "-":
        result = a - b
    elif op in ("×", "x", "*"):
        result = a * b
    elif op in ("÷", "/"):
        if b == 0:
            return None
        result = a / b
    else:
        return None
    exp = _num(expected)
    if exp is None:
        return None
    return abs(result - exp) < 1e-9


def verify_sequence_next(terms: list[float], expected_next: float) -> bool | None:
    """Verify arithmetic-sequence continuation. Returns None if not arithmetic."""
    if len(terms) < 2:
        return None
    diffs = [round(terms[i + 1] - terms[i], 9) for i in range(len(terms) - 1)]
    if len(set(diffs)) != 1:
        return None
    return abs((terms[-1] + diffs[0]) - expected_next) < 1e-9
