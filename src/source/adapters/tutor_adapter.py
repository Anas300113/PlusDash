"""Adapter for jhammant/11plus-tutor + UKIQEAI/11plus-tutor.
Both repos share the same content lineage (identical all_questions.json
lineage), so one adapter covers both. Content is treated separately
from architecture; rights default to licensed (MIT + generated/PD)."""
from __future__ import annotations

from typing import Any

from src.source.adapters.base import BaseAdapter

_SUBJECT_MAP = {
    "mathematics": "maths",
    "maths": "maths",
    "english": "english",
    "verbal_reasoning": "verbal_reasoning",
    "verbal": "verbal_reasoning",
    "non_verbal_reasoning": "non_verbal_reasoning",
    "nonverbal": "non_verbal_reasoning",
}

_FORMAT_MAP = {
    "multiple_choice": "mcq",
    "short_answer": "free_text",
    "long_answer": "free_text",
    "fill_blank": "cloze",
    "matching": "matching",
    "ordering": "ordering",
    "true_false": "mcq",
    "diagram": "image_choice",
}


class TutorAdapter(BaseAdapter):
    source_name = "11plus-tutor"

    def to_canonical(self, external: dict[str, Any]) -> dict[str, Any]:
        options = external.get("options") or []
        options_json = [
            {"letter": chr(65 + i), "text": str(o)} for i, o in enumerate(options)
        ]
        correct = str(external.get("correct_answer", ""))
        idx = external.get("correct_index")
        if idx is not None and 0 <= int(idx) < len(options_json):
            correct = options_json[int(idx)]["letter"]
        return {
            "subject": _SUBJECT_MAP.get(str(external.get("subject", "")), "maths"),
            "topic": str(external.get("topic", "general")),
            "subtopic": str(external.get("subtopic", "") or ""),
            "question_type": _FORMAT_MAP.get(
                str(external.get("format", "multiple_choice")), "mcq"),
            "difficulty": external.get("difficulty"),
            "question_text": str(external.get("question_text", "")),
            "context": str(external.get("context", "") or ""),
            "correct_answer": correct,
            "options_json": options_json,
            "explanation": str(external.get("worked_solution", "") or ""),
            "worked_solution": str(external.get("worked_solution", "") or ""),
            "hint": str(external.get("hint", "") or ""),
            "exam_board": "mixed",
            "source_question_id": str(external.get("id", "")),
        }
