"""SQLAlchemy models. Table prefixes enforce domain separation:
source_* (provenance), canonical_* (educational content),
curriculum_* (lessons), assessment_* (exams), learning_* (students),
ai_* (AI jobs/outputs). Never collapse these into one table."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import ssl

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String as SQLString, Text,
    UniqueConstraint, create_engine, make_url,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class String(SQLString):
    """Default unspecified app strings to an indexed-safe MySQL VARCHAR."""

    def __init__(self, length: int | None = 255, **kwargs):
        super().__init__(255 if length is None else length, **kwargs)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # datetime.now(timezone.utc) avoids the datetime.utcnow() deprecation
    # (py3.12+). .replace(tzinfo=None) keeps the return naive so existing
    # offset-naive stored datetimes and subtractions keep working.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- SOURCE domain ----------------

class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    repo_name: Mapped[str] = mapped_column(String, nullable=False)
    repo_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_path: Mapped[str] = mapped_column(String, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_type: Mapped[str] = mapped_column(String, nullable=False, default="")
    commit_sha: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    rights_status: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    rights_note: Mapped[str] = mapped_column(Text, default="")
    ingestion_batch: Mapped[str] = mapped_column(String, nullable=False, default="")
    ingestion_version: Mapped[str] = mapped_column(String, nullable=False, default="0.1.0")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SourcePage(Base):
    __tablename__ = "source_pages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("source_documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="")
    text_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    ocr_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    ocr_engine: Mapped[str] = mapped_column(String, default="", server_default="")
    ocr_version: Mapped[str] = mapped_column(String, default="", server_default="")


class SourceAsset(Base):
    __tablename__ = "source_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("source_documents.id"), index=True)
    page_id: Mapped[str] = mapped_column(String, ForeignKey("source_pages.id"), nullable=True)
    asset_type: Mapped[str] = mapped_column(String, nullable=False, default="raster")
    mime_type: Mapped[str] = mapped_column(String, nullable=False, default="")
    sha256: Mapped[str] = mapped_column(String, nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(String, nullable=False, default="")
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    alt_text: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")


class QuestionOccurrence(Base):
    __tablename__ = "question_occurrences"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_question_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_questions.id"), nullable=True, index=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("source_documents.id"), index=True)
    page_id: Mapped[str] = mapped_column(String, ForeignKey("source_pages.id"))
    question_number: Mapped[str] = mapped_column(String, default="")
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_answer: Mapped[str] = mapped_column(String, default="")
    extraction_run: Mapped[str] = mapped_column(String, default="")
    extraction_version: Mapped[str] = mapped_column(String, default="0.1.0")
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------- CANONICAL domain ----------------

class CanonicalSubject(Base):
    __tablename__ = "canonical_subjects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class CanonicalTopic(Base):
    __tablename__ = "canonical_topics"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey("canonical_subjects.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class CanonicalSkill(Base):
    __tablename__ = "canonical_skills"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("canonical_topics.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class CanonicalQuestionType(Base):
    __tablename__ = "canonical_question_types"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    requires_options: Mapped[bool] = mapped_column(Boolean, default=False)


class CanonicalQuestion(Base):
    __tablename__ = "canonical_questions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String, nullable=False, index=True)
    subtopic: Mapped[str] = mapped_column(String, default="")
    question_type: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_question_types.id"), index=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skill_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    question_text: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")
    correct_answer: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    worked_solution: Mapped[str] = mapped_column(Text, default="")
    hint: Mapped[str] = mapped_column(Text, default="")
    # Trustworthy-question contract: explicit verification states.
    #   answer_status:      missing | candidate | verified | conflicting
    #   explanation_status: missing | candidate | verified
    # A populated correct_answer/explanation alone is NEVER proof of approval.
    answer_status: Mapped[str] = mapped_column(
        String, default="missing", server_default="missing", index=True)
    explanation_status: Mapped[str] = mapped_column(
        String, default="missing", server_default="missing")
    answer_evidence: Mapped[str] = mapped_column(
        Text, default="", server_default="")
    explanation_evidence: Mapped[str] = mapped_column(
        Text, default="", server_default="")
    extraction_warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String, default="en")
    exam_board: Mapped[str] = mapped_column(String, default="")
    region: Mapped[str] = mapped_column(String, default="")
    fingerprint: Mapped[str] = mapped_column(String, default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QuestionRegionBoard(Base):
    """Normalised canonical ↔ region/board association.

    Each source record's region/board assertion is preserved individually
    instead of being collapsed to a single canonical value. Conflicting
    assertions across sources are flagged, not silently discarded.
    """
    __tablename__ = "question_region_board"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_questions.id"), index=True,
        nullable=False)
    region: Mapped[str] = mapped_column(String, default="", server_default="")
    board: Mapped[str] = mapped_column(String, default="", server_default="")
    source_document_id: Mapped[str] = mapped_column(
        String, ForeignKey("source_documents.id"), index=True, nullable=True)
    source_question_id: Mapped[str] = mapped_column(
        String, default="", server_default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    ingestion_batch: Mapped[str] = mapped_column(String, default="",
                                                 server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("question_id", "source_document_id",
                         "source_question_id",
                         name="uq_question_region_board_source"),
    )


class CorpusSnapshot(Base):
    """Cumulative corpus snapshot taken after each ingestion run.

    Immutable per-run record of whole-corpus state: total questions,
    occurrences, approved counts, and per-source breakdown. Enables
    incremental runs to reconcile against whole-corpus state (Gate 3).
    """
    __tablename__ = "corpus_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    total_occurrences: Mapped[int] = mapped_column(Integer, default=0)
    total_approved: Mapped[int] = mapped_column(Integer, default=0)
    total_pending_review: Mapped[int] = mapped_column(Integer, default=0)
    per_source_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("pipeline_runs.id"), index=True, nullable=True)


class QuestionReviewStatus(Base):
    __tablename__ = "question_review_status"
    question_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_questions.id"), primary_key=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="discovered", index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="ingestion")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Audit: who last decided, when, and why (human review trail).
    # server_default required so the additive ALTER satisfies SQLite NOT NULL
    # on existing rows (see src/core/migrations.py).
    reviewer: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="")
    decision: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QuestionReviewEvent(Base):
    """Append-only audit log of review decisions and edits.

    Never overwritten: each approval / rejection / edit records the acting
    reviewer, a UTC timestamp, the decision, and a reason. This is the
    authoritative review history required by the trustworthy-question contract.
    """
    __tablename__ = "question_review_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_questions.id"), index=True)
    action: Mapped[str] = mapped_column(
        String, nullable=False, index=True)  # edit | approve | reject | verify_answer | verify_explanation
    reviewer: Mapped[str] = mapped_column(String, nullable=False, default="")
    from_status: Mapped[str] = mapped_column(String, default="")
    to_status: Mapped[str] = mapped_column(String, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AssessmentExamBoard(Base):
    __tablename__ = "assessment_exam_boards"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    regions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AssessmentExam(Base):
    __tablename__ = "assessment_exams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_board_id: Mapped[str] = mapped_column(
        String, ForeignKey("assessment_exam_boards.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, default="")
    subjects_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AssessmentExamSection(Base):
    __tablename__ = "assessment_exam_sections"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_id: Mapped[str] = mapped_column(
        String, ForeignKey("assessment_exams.id"), index=True)
    section_number: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, default="")
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    marks_available: Mapped[int] = mapped_column(Integer, default=0)
    instructions: Mapped[str] = mapped_column(Text, default="")


class CurriculumLesson(Base):
    __tablename__ = "curriculum_lessons"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_topics.id"), index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class CurriculumStrategy(Base):
    __tablename__ = "curriculum_strategies"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_topics.id"), index=True)
    question_type: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class CurriculumWorkedExample(Base):
    __tablename__ = "curriculum_worked_examples"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_topics.id"), index=True)
    question_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("canonical_questions.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, default="")


class CurriculumCommonMistake(Base):
    __tablename__ = "curriculum_common_mistakes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_topics.id"), index=True)
    mistake_text: Mapped[str] = mapped_column(Text, default="")
    explanation_markdown: Mapped[str] = mapped_column(Text, default="")


class LearningStudent(Base):
    __tablename__ = "learning_students"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_exam: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LearningStudySession(Base):
    """Study session + practice/mock state machine.

    ``session_type``  : learn | practice | review | mock | diagnostic | catch_up
    ``state``         : session lifecycle, see src/learning/session.py
    ``question_order_json`` is the frozen ordering for the session so an
    interrupted session can be resumed deterministically.
    All new columns carry a ``server_default`` so they can be appended to an
    existing SQLite database by src/core/migrations.py.
    """
    __tablename__ = "learning_study_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), index=True)
    session_type: Mapped[str] = mapped_column(String, default="practice")
    state: Mapped[str] = mapped_column(
        String, default="started", server_default="started", index=True)
    planned_duration_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    actual_duration_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    goals_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_activities_json: Mapped[list | None] = mapped_column(
        JSON, nullable=True)
    question_order_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    current_index: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    skipped_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- derived helpers (no extra columns, no duplicated state) ---
    @property
    def question_order(self) -> list[str]:
        return list(self.question_order_json or [])

    @property
    def completion_state(self) -> str:
        """planned | in_progress | complete | abandoned."""
        if self.state in ("complete", "abandoned"):
            return self.state
        return "in_progress" if self.question_order else "planned"

    @property
    def questions_remaining(self) -> int:
        return max(0, len(self.question_order) - (self.current_index or 0))

    @property
    def progress(self) -> float:
        total = len(self.question_order)
        if not total:
            return 0.0
        return min(1.0, (self.current_index or 0) / total)


class LearningQuestionAttempt(Base):
    """Evidence of student performance. This is the authoritative record of
    what a student did; it is never overwritten by scheduling state.

    ``action``          : answer | skip | retry (retry = re-answer of a question)
    ``attempt_number``  : 1-based attempt of this question within the session
    ``hint_used``       : student opened hint/explanation before answering
    ``review_item_id``  : soft reference to learning_review_items.id when the
                          attempt came from spaced-review practice
    Accuracy statistics only count ``action == 'answer'`` so that skips and
    retries do not distort mastery.
    """
    __tablename__ = "learning_question_attempts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), index=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_study_sessions.id"), index=True)
    question_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_questions.id"), index=True)
    chosen_answer: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    time_taken_ms: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(
        String, default="answer", server_default="answer", index=True)
    attempt_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1")
    hint_used: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0")
    review_item_id: Mapped[str] = mapped_column(
        String, default="", server_default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LearningTopicMastery(Base):
    """Topic-level mastery aggregate (derived from attempts)."""
    __tablename__ = "learning_topic_mastery"
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_topics.id"), primary_key=True)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    times_practiced: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)




class LearningSkillMastery(Base):
    """Skill-level mastery aggregate, derived from attempts joined to the
    ``skill_ids`` declared on CanonicalQuestion. Sits between attempt
    evidence and TopicMastery; it does not schedule anything itself."""
    __tablename__ = "learning_skill_mastery"
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(
        String, ForeignKey("canonical_skills.id"), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String, default="", server_default="")
    subject: Mapped[str] = mapped_column(String, default="", server_default="")
    accuracy: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    times_practiced: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    times_correct: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)


class LearningReviewItem(Base):
    """What should be reviewed, and when.

    This is *scheduling state*, deliberately separate from:
      * ``LearningQuestionAttempt`` - evidence of what happened
      * ``LearningSkillMastery`` / ``LearningTopicMastery`` - learning state
      * ``CanonicalQuestion`` - the educational content itself
      * ``LearningRecommendation`` - what to do next

    ``source_type``/``source_id`` is a soft reference (no FK) so the same
    table can schedule questions now, and lesson / strategy / worked-example
    review later, without introducing a broad ``LearningItem`` abstraction.

    Scheduling is a deterministic interval ladder (see src/learning/review.py).
    FSRS is deliberately NOT implemented.
    """
    __tablename__ = "learning_review_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), index=True)
    source_type: Mapped[str] = mapped_column(
        String, default="question", server_default="question", index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str] = mapped_column(String, default="", server_default="")
    topic_id: Mapped[str] = mapped_column(
        String, default="", server_default="", index=True)
    question_type: Mapped[str] = mapped_column(
        String, default="", server_default="")
    skill_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(
        String, default="learning", server_default="learning", index=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    interval_days: Mapped[float] = mapped_column(
        Float, default=1.0, server_default="1")
    review_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    correct_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    consecutive_correct: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    last_result: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_reason: Mapped[str] = mapped_column(String, default="", server_default="")
    origin_attempt_id: Mapped[str] = mapped_column(
        String, default="", server_default="")
    origin_session_id: Mapped[str] = mapped_column(
        String, default="", server_default="")
    review_history_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("student_id", "source_type", "source_id",
                         name="uq_review_item_source"),
    )


class LearningRecommendation(Base):
    """Deterministic recommendation of what the student should do next.

    ``kind``: learn | practice | review | mock | catch_up
    """
    __tablename__ = "learning_recommendations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("learning_students.id"), index=True)
    kind: Mapped[str] = mapped_column(
        String, default="practice", server_default="practice", index=True)
    reason: Mapped[str] = mapped_column(String, default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String, default="open", server_default="open", index=True)
    question_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    topic_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    skill_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    review_item_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AIJob(Base):
    __tablename__ = "ai_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_input: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String, default="")
    model_version: Mapped[str] = mapped_column(String, default="")
    prompt_version: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    error_message: Mapped[str] = mapped_column(Text, default="")


class AIOutput(Base):
    __tablename__ = "ai_outputs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("ai_jobs.id"), index=True)
    output_type: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AIValidation(Base):
    __tablename__ = "ai_validations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ai_output_id: Mapped[str] = mapped_column(
        String, ForeignKey("ai_outputs.id"), index=True)
    validator_type: Mapped[str] = mapped_column(String, default="")
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AIApproval(Base):
    __tablename__ = "ai_approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ai_output_id: Mapped[str] = mapped_column(
        String, ForeignKey("ai_outputs.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    reviewer_id: Mapped[str] = mapped_column(String, default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    pipeline_version: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    checkpoint: Mapped[str] = mapped_column(String, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True,
                                                          default=None)


def get_engine(url: str):
    """Create an engine with verified TLS for the managed MySQL service.

    The managed platform supplies a mysql:// URL with an ``ssl`` query flag.
    SQLAlchemy's default MySQL driver is not installed, so normalize it to
    PyMySQL and translate that flag into a verified SSLContext. SQLite test
    URLs pass through unchanged.
    """
    parsed = make_url(url)
    connect_args: dict = {}
    if parsed.drivername in ("mysql", "mysql+pymysql", "mariadb"):
        query = dict(parsed.query)
        ssl_requested = query.pop("ssl", None)
        ssl_mode = query.pop("ssl-mode", query.pop("ssl_mode", None))
        if str(ssl_requested).strip().lower() in {"0", "false", "off", "no"}:
            raise ValueError("Managed MySQL connections require TLS.")
        if str(ssl_mode).strip().lower() in {"disable", "disabled", "false"}:
            raise ValueError("Managed MySQL connections require TLS.")
        ca_file = os.environ.get("PLUS_MYSQL_SSL_CA")
        context = ssl.create_default_context(cafile=ca_file or None)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        connect_args["ssl"] = context
        parsed = parsed.set(
            drivername="mysql+pymysql",
            query=query,
        )
        return create_engine(
            parsed, echo=False, future=True, pool_pre_ping=True,
            pool_recycle=1800, connect_args=connect_args)
    return create_engine(parsed, echo=False, future=True)


def get_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(engine) -> None:
    """Create the schema and apply additive column migrations.

    Delegates to src/core/migrations.ensure_schema so an existing database
    (e.g. ./elevenplus.db) gains new learning-layer columns without a wipe.
    Alembic remains the deferred long-term answer for destructive changes.
    """
    from src.core.migrations import ensure_schema

    ensure_schema(engine)
