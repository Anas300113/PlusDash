"""Canonical question validators."""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_STATUSES = {
    "discovered", "extracted", "ai_reviewed",
    "validation_required", "approved", "rejected",
}

VALID_QUESTION_TYPES = {
    "mcq", "numeric", "free_text", "multi_select", "matching",
    "ordering", "cloze", "image_choice", "creative_writing", "unknown_custom",
}

VALID_SUBJECTS = {"maths", "english", "verbal_reasoning", "non_verbal_reasoning"}

VALID_RIGHTS = {"owned", "licensed", "permission_required", "reference_only", "unknown"}


@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def validate_canonical_question(q: dict) -> ValidationResult:
    issues: list[ValidationIssue] = []

    for f in ("subject", "topic", "question_type", "correct_answer"):
        if not q.get(f):
            issues.append(ValidationIssue(f, f"missing required field: {f}"))

    if q.get("subject") and q["subject"] not in VALID_SUBJECTS:
        issues.append(ValidationIssue("subject", f"unknown subject: {q['subject']}"))

    qtype = q.get("question_type")
    if qtype and qtype not in VALID_QUESTION_TYPES:
        issues.append(ValidationIssue("question_type", f"unknown type: {qtype}"))

    if qtype in ("mcq", "multi_select", "image_choice"):
        options = q.get("options_json") or []
        if len(options) < 2:
            issues.append(ValidationIssue("options_json", "choice question needs >= 2 options"))
        answer = str(q.get("correct_answer", ""))
        letters = [str(o.get("letter", o.get("id", ""))).upper()
                   for o in options if isinstance(o, dict)]
        if letters and answer.upper() not in letters and answer not in [
                o if isinstance(o, str) else "" for o in options]:
            issues.append(ValidationIssue("correct_answer", "answer not among options"))

    diff = q.get("difficulty")
    if diff is not None and not (1 <= int(diff) <= 5):
        issues.append(ValidationIssue("difficulty", "difficulty must be 1-5"))

    return ValidationResult(passed=not [i for i in issues if i.severity == "error"],
                            issues=issues)


def validate_rights_status(status: str) -> bool:
    return status in VALID_RIGHTS
