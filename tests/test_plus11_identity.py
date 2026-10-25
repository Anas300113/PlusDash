"""Security and learning-flow tests for the server-verified Plus11 identity bridge."""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.plus11 import get_db
from src.core.database import (
    CanonicalQuestion,
    LearningQuestionAttempt,
    LearningStudent,
    QuestionReviewStatus,
    get_engine,
    get_session_factory,
    init_db,
)

SECRET = "plus11-test-secret-never-used-outside-isolated-tests"
PROJECT_ID = "plus11-test-project"


def _token(open_id: str, *, project_id: str = PROJECT_ID, expires: int | None = None, name: str = "Sam") -> str:
    now = int(time.time())
    claims = {
        "appId": project_id,
        "openId": open_id,
        "name": name,
        "iat": now,
        "exp": expires if expires is not None else now + 300,
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """Bind all account endpoints to a fresh, file-backed SQLite database."""
    monkeypatch.setenv("MANUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("MANUS_PROJECT_ID", PROJECT_ID)
    engine = get_engine(f"sqlite:///{tmp_path / 'plus11-auth-test.sqlite'}")
    init_db(engine)
    session_factory = get_session_factory(engine)

    def isolated_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _headers(open_id: str = "provider-user-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(open_id)}"}


def _approved_question(session_factory) -> str:
    question_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(CanonicalQuestion(
            id=question_id,
            subject="maths",
            topic="maths-arithmetic",
            question_type="mcq",
            question_text="What is 2 + 2?",
            correct_answer="B",
            explanation="Two pairs make four.",
            options_json=[{"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}],
        ))
        db.add(QuestionReviewStatus(question_id=question_id, status="approved"))
        db.commit()
    finally:
        db.close()
    return question_id


def test_identity_requires_valid_signature_expiry_and_project(api):
    client, _ = api
    assert client.get("/api/me/profile").status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": f"Bearer {_token('user', expires=int(time.time()) - 1)}"}).status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": f"Bearer {_token('user', project_id='another-project')}"}).status_code == 401


def test_profile_uses_opaque_stable_id_and_never_returns_open_id(api):
    client, session_factory = api
    first = client.get("/api/me/profile", headers=_headers("provider-user-1"))
    second = client.get("/api/me/profile", headers=_headers("provider-user-1",))
    assert first.status_code == second.status_code == 200
    assert first.json()["student_id"].startswith("p11_")
    assert first.json()["student_id"] == second.json()["student_id"]
    assert "provider-user-1" not in first.text
    assert "openId" not in first.json()
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 0
    finally:
        db.close()


def test_profile_update_creates_the_learner_only_on_a_mutation(api):
    client, session_factory = api
    read = client.get("/api/me/profile", headers=_headers())
    assert read.status_code == 200
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 0
    finally:
        db.close()

    changed = client.patch(
        "/api/me/profile", headers=_headers(), json={"display_name": "Sam Learner"},
    )
    assert changed.status_code == 200
    assert changed.json()["display_name"] == "Sam Learner"
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 1
    finally:
        db.close()


def test_catalog_includes_only_approved_content_and_never_answer_keys(api):
    client, session_factory = api
    approved_id = _approved_question(session_factory)
    db = session_factory()
    pending_id = str(uuid.uuid4())
    try:
        db.add(CanonicalQuestion(
            id=pending_id, subject="english", topic="unreviewed", question_type="mcq",
            question_text="Pending question?", correct_answer="A", explanation="Private.",
            options_json=[{"letter": "A", "text": "One"}],
        ))
        db.add(QuestionReviewStatus(question_id=pending_id, status="pending"))
        db.commit()
    finally:
        db.close()

    response = client.get("/api/me/catalog", headers=_headers())
    assert response.status_code == 200
    payload = response.json()
    assert [subject["id"] for subject in payload["subjects"]] == ["maths"]
    assert payload["subjects"][0]["topics"][0]["approved_question_count"] == 1
    assert approved_id not in response.text
    assert "correct_answer" not in response.text
    assert "explanation" not in response.text
    assert "Pending question" not in response.text


def test_practice_hides_answers_until_check_and_enforces_session_ownership(api):
    client, session_factory = api
    question_id = _approved_question(session_factory)
    start_body = {
        "subject_id": "maths",
        "topic_id": "maths-arithmetic",
        "idempotency_key": str(uuid.uuid4()),
    }
    first = client.post("/api/me/practice/sessions", headers=_headers(), json=start_body)
    duplicate = client.post("/api/me/practice/sessions", headers=_headers(), json=start_body)
    assert first.status_code == duplicate.status_code == 200
    session = first.json()
    assert session["session_id"] == duplicate.json()["session_id"]
    question = session["current_question"]
    assert question["id"] == question_id
    assert "correct_answer" not in question
    assert "explanation" not in question
    assert "answer" not in question

    other_learner = client.get(
        f"/api/me/practice/sessions/{session['session_id']}",
        headers=_headers("different-provider-user"),
    )
    assert other_learner.status_code == 404

    event_id = str(uuid.uuid4())
    answer_body = {
        "question_id": question_id,
        "chosen_answer": "B",
        "idempotency_key": event_id,
        "time_taken_ms": 12_000,
        "hint_used": False,
        "action": "answer",
    }
    checked = client.post(
        f"/api/me/practice/sessions/{session['session_id']}/answers",
        headers=_headers(), json=answer_body,
    )
    repeated = client.post(
        f"/api/me/practice/sessions/{session['session_id']}/answers",
        headers=_headers(), json=answer_body,
    )
    assert checked.status_code == repeated.status_code == 200
    assert checked.json()["is_correct"] is True
    assert checked.json()["explanation"] == "Two pairs make four."
    assert repeated.json()["is_correct"] is True
    db = session_factory()
    try:
        assert db.query(LearningQuestionAttempt).count() == 1
    finally:
        db.close()
