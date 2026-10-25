"""Adapter for the private 11-dump corpus. Files (PDF/PPTX/ZIP/image)
are registered as source documents; content extraction happens in the
ingestion pipeline. Rights default to unknown and must be reviewed."""
from __future__ import annotations

from typing import Any

from src.source.adapters.base import BaseAdapter


class DumpAdapter(BaseAdapter):
    source_name = "11-dump"

    def to_canonical(self, external: dict[str, Any]) -> dict[str, Any]:
        # 11-dump items enter as raw occurrences, not pre-structured
        # questions; the pipeline promotes them. This keeps one code path.
        return {
            "subject": str(external.get("subject", "") or ""),
            "topic": str(external.get("topic", "") or ""),
            "question_type": str(external.get("question_type", "unknown_custom")),
            "question_text": str(external.get("question_text", "")),
            "correct_answer": str(external.get("correct_answer", "")),
            "source_question_id": str(external.get("occurrence_id", "")),
        }
