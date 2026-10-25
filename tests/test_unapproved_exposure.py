"""Gate 2: student-facing exposure matrix for unapproved imported questions.

Every route that can return question content, answers, explanations or
feedback is tested against records in each unapproved state -- plus
incorrectly classified records (wrong case / whitespace statuses) and
unknown ids. The reviewer workbench remains the deliberate verification
route. This gate does NOT change (and does not solve) the documented
student-identity limitations.
"""
from __future__ import annotations

import uuid

import pytest

httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src.core.database import (  # noqa: E402
    CanonicalQuestion, QuestionReviewStatus, get_engine,
    get_session_factory, init_db,
)
import src.api.main as api_main  # noqa: E402

UNAPPROVED_STATES = ["validation_required", "extracted", "pending",
                     "rejected", "Approved", "approved ", "APPROVED"]


def _mk_question(session, text="What is 256 x 4?", answer="B"):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text=text, correct_answer=answer,
        explanation="Because 256 x 4 = 1024.",
        options_json=[{"letter": "A", "text": "984"},
                      {"letter": "B", "text": "1024"}],
        fingerprint=str(uuid.uuid4()))
    session.add(q)
    session.flush()
    return q


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh API bound to a DB with one question per status state."""
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    ids = {}
    for state in UNAPPROVED_STATES:
        q = _mk_question(s, text=f"unapproved-{state!r}-256x4")
        s.add(QuestionReviewStatus(question_id=q.id, status=state))
        ids[state] = q.id
    approved = _mk_question(s, text="approved-256x4")
    s.add(QuestionReviewStatus(question_id=approved.id, status="approved"))
    ids["approved"] = approved.id
    s.commit()
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app), ids


def test_question_list_never_contains_unapproved_or_misclassified(env):
    c, ids = env
    listed = {r["id"] for r in c.get("/api/questions", params={
        "limit": 100}).json()}
    for state in UNAPPROVED_STATES:
        assert ids[state] not in listed, state
    assert ids["approved"] in listed        # positive control


@pytest.mark.parametrize("state", UNAPPROVED_STATES)
def test_explain_route_rejects_every_unapproved_state(env, state):
    c, ids = env
    r = c.get(f"/api/explain/{ids[state]}")
    assert r.status_code == 403
    # the refusal must not leak the answer or explanation
    body = r.text.lower()
    assert "1024" not in body and "because 256" not in body


def test_explain_unknown_id_is_404_not_a_probe(env):
    c, _ = env
    assert c.get(f"/api/explain/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize("state", UNAPPROVED_STATES)
def test_attempt_submission_rejects_unapproved(env, state):
    c, ids = env
    r = c.post("/api/attempts", json={
        "student_id": "s1", "session_id": str(uuid.uuid4()),
        "question_id": ids[state], "chosen_answer": "B"})
    assert r.status_code == 403
    assert "1024" not in r.text


def test_session_start_excludes_unapproved_question_ids(env):
    c, ids = env
    r = c.post("/api/sessions/start", json={
        "student_id": "s1",
        "question_ids": [ids["validation_required"], ids["approved"]]})
    assert r.status_code == 200
    order = r.json()["question_order"]
    assert ids["approved"] in order
    assert ids["validation_required"] not in order


def test_mock_assembly_uses_only_approved_questions(env, tmp_path):
    from src.assessment.assembler import assemble_generated
    engine = get_engine(f"sqlite:///{tmp_path / 'asm.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    ap = _mk_question(s, text="approved asm q")
    s.add(QuestionReviewStatus(question_id=ap.id, status="approved"))
    un = _mk_question(s, text="unapproved asm q")
    s.add(QuestionReviewStatus(question_id=un.id,
                               status="validation_required"))
    s.commit()
    paper = assemble_generated(s, str(uuid.uuid4()),
                               [{"subject": "maths", "count": 10}])
    assert un.id not in paper["questions"]
    assert ap.id in paper["questions"]      # positive control
    s.close()


def test_reviewer_workbench_is_the_deliberate_gated_route(env, monkeypatch):
    """The only route exposing unapproved question detail is the reviewer
    workbench, and it fails closed: 503 when no token is configured,
    403 for a wrong token."""
    monkeypatch.delenv("PLUS_REVIEWER_TOKEN", raising=False)
    c, ids = env
    assert c.get("/api/review-queue").status_code == 503
    assert c.get(f"/api/review/{ids['validation_required']}").status_code \
        == 503
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    assert c.get("/api/review-queue",
                 headers={"X-Reviewer-Token": "wrong"}).status_code == 403
