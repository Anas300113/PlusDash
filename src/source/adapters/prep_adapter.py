"""Adapter for SahirVhora/11plus-prep regional JSON banks.
Preserves region + exam board metadata; normalises the A-E answer
letter from options text."""
from __future__ import annotations

import re
from typing import Any

from src.source.adapters.base import BaseAdapter

_SUBJECT_MAP = {
    "maths": "maths",
    "english": "english",
    "verbal": "verbal_reasoning",
    "nonverbal": "non_verbal_reasoning",
}

_FORMAT_MAP = {
    "mcq": "mcq",
    "text-input": "free_text",
    "creative-writing": "creative_writing",
    "written-answer": "free_text",
    "cloze": "cloze",
}


class PrepAdapter(BaseAdapter):
    source_name = "11plus-prep"
    licence_note = "MIT License, Copyright (c) 2026 Sahir Vhora"

    def to_canonical(self, external: dict[str, Any]) -> dict[str, Any]:
        options = external.get("options") or []
        options_json = []
        for o in options:
            m = re.match(r"^([A-E])\)\s*(.*)$", str(o).strip())
            if m:
                options_json.append({"letter": m.group(1), "text": m.group(2)})
            else:
                options_json.append(
                    {"letter": chr(65 + len(options_json)), "text": str(o)})
        qtype = str(external.get("type", "mcq"))
        if external.get("format"):
            qtype = str(external["format"])
        return {
            "subject": _SUBJECT_MAP.get(str(external.get("subject", "")), "maths"),
            "topic": str(external.get("topic", "general")),
            "question_type": _FORMAT_MAP.get(qtype, "mcq"),
            "difficulty": external.get("difficulty"),
            "question_text": str(external.get("question", "")),
            "context": str(external.get("context", "") or ""),
            "correct_answer": str(external.get("answer", "")).strip().upper()[:1],
            "options_json": options_json,
            "explanation": str(external.get("explanation", "")),
            "exam_board": str(external.get("examBoard", "") or "mixed"),
            "region": str(external.get("region", "") or ""),
            "source_question_id": str(external.get("id", "")),
        }
