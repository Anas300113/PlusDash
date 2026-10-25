"""API tests via FastAPI TestClient (needs httpx installed).

Covers both the legacy endpoints (kept for compatibility) and the
learning-layer endpoints added in the session/state-machine phase.
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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "api.db"
    url = f"sqlite:///{db_file}"
    engine = get_engine(url)
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          explanation="Because 2+2=4.",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    s.add(q)
    s.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    s.commit()
    qid = q.id
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    c = TestClient(api_main.app)
    return c, qid


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json() == {"ok": True}


def test_questions_only_approved(client):
    c, qid = client
    rows = c.get("/api/questions").json()
    assert [r["id"] for r in rows] == [qid]


def test_attempt_flow(client):
    c, qid = client
    sid = c.post("/api/sessions", params={"student_id": "s1"}).json()["session_id"]
    r = c.post("/api/attempts", json={"student_id": "s1", "session_id": sid,
                                      "question_id": qid, "chosen_answer": "B"})
    assert r.json()["is_correct"] is True
    prog = c.get("/api/progress/s1").json()
    assert "weak_topics" in prog


def test_practice_page_served(client):
    c, _ = client
    r = c.get("/practice")
    assert r.status_code == 200 and "11+ Practice" in r.text


def test_dashboard_pages_served(client):
    c, _ = client
    for path, marker in [("/", "11+ Preparation Platform"),
                         ("/learn", "Learn"), ("/mocks", "Mock Exams"),
                         ("/progress", "Progress"),
                         ("/parent", "Parent dashboard")]:
        r = c.get(path)
        assert r.status_code == 200 and marker in r.text, path


def test_curriculum_and_parent_endpoints(client):
    c, _ = client
    assert c.get("/api/curriculum/maths-fractions").status_code == 200
    assert "practice_completed" in c.get("/api/parent/s1").json()


def test_exam_assemble_endpoint(client):
    c, qid = client
    exam = c.post("/api/exams", json={"name": "E"}).json()
    out = c.post(f"/api/exams/{exam['exam_id']}/assemble",
                 json={"mode": "generated",
                       "sections": [{"subject": "maths", "count": 5}]}).json()
    assert out["questions"] == [qid]


def test_session_start_freezes_order_and_returns_state(client):
    c, qid = client
    out = c.post("/api/sessions/start", json={
        "student_id": "s1", "session_type": "practice",
        "planned_duration_seconds": 600,
        "goals": {"topic": "maths-arithmetic"}}).json()
    assert out["state"] == "started" and out["total"] == 1
    assert out["question_order"] == [qid]
    state = c.get(f"/api/sessions/{out['session_id']}").json()
    assert state["current_question_id"] == qid
    assert state["current_question"]["question_text"] == "2+2?"
    assert state["goals"]["topic"] == "maths-arithmetic"
    assert state["resumable"] is True
    assert state["progress"] == 0.0


def test_session_answer_rejects_non_current_question(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    r = c.post(f"/api/sessions/{sid}/answer",
               json={"question_id": "not-the-current-one", "chosen_answer": "B"})
    assert r.status_code == 400


def test_session_abandon_keeps_evidence(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    c.post(f"/api/sessions/{sid}/answer",
           json={"question_id": qid, "chosen_answer": "B"})
    out = c.post(f"/api/sessions/{sid}/abandon").json()
    assert out["state"] == "abandoned" and out["resumable"] is False
    assert c.post(f"/api/sessions/{sid}/answer",
                  json={"question_id": qid, "chosen_answer": "A"}
                  ).status_code == 400


def test_session_answer_feedback_skip_retry_complete(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    # wrong answer -> explanation + review item scheduled
    wrong = c.post(f"/api/sessions/{sid}/answer",
                   json={"question_id": qid, "chosen_answer": "A"}).json()
    assert wrong["is_correct"] is False
    assert wrong["explanation"] == "Because 2+2=4."
    assert wrong["feedback"]["correct_answer"] == "B"
    assert wrong["feedback"]["review_prompt"]
    assert wrong["review_item_id"]
    assert wrong["session"]["index"] == 1

    # retry: reopen the missed question, then answer it correctly
    retry = c.post(f"/api/sessions/{sid}/retry").json()
    assert retry["question_id"] == qid and retry["hint"] == ""
    retry_out = c.post(f"/api/sessions/{sid}/answer",
                       json={"question_id": qid, "chosen_answer": "B",
                             "action": "retry"}).json()
    assert retry_out["is_correct"] is True
    assert retry_out["session"]["attempt_count"] == 2

    results = c.post(f"/api/sessions/{sid}/complete").json()
    assert results["answered"] == 2
    assert results["correct"] == 1
    assert results["retries"] == 1
    assert results["review_items_created"] == 1
    assert results["state"] == "complete"
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "complete"
    # terminal session rejects further work
    assert c.post(f"/api/sessions/{sid}/answer",
                  json={"question_id": qid, "chosen_answer": "B"}
                  ).status_code == 400


def test_session_skip_records_evidence_without_counting_as_wrong(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    skip = c.post(f"/api/sessions/{sid}/skip", json={}).json()
    assert skip["action"] == "skip"
    assert skip["is_correct"] is False          # no answer was given
    assert skip["session"]["skipped_ids"] == [qid]
    assert skip["review_item_id"]               # a skip is a knowledge gap
    results = c.get(f"/api/sessions/{sid}/results").json()
    assert results["answered"] == 0 and results["skipped"] == 1
    assert results["accuracy"] == 0.0           # no measured answers yet


def test_review_queue_endpoint_and_review_session(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    c.post(f"/api/sessions/{sid}/answer",
           json={"question_id": qid, "chosen_answer": "A"})  # wrong
    reviews = c.get("/api/reviews/s1").json()
    assert reviews["summary"]["total"] == 1
    assert reviews["summary"]["due_now"] == 0   # scheduled for tomorrow
    assert reviews["due"] == []

            # Force the item due, then start a review session from the queue.
    from src.core.database import LearningReviewItem
    s = api_main._Session()
    item = s.query(LearningReviewItem).one()
    item.due_at = item.created_at
    s.commit()
    s.close()
    reviews = c.get("/api/reviews/s1").json()
    assert reviews["summary"]["due_now"] == 1
    assert reviews["due"][0]["topic"] == "maths-arithmetic"
    assert reviews["due"][0]["due_reason"] == "incorrect"
    review_session = c.post("/api/sessions", params={
        "student_id": "s1", "session_type": "review",
        "from_review_queue": "true"}).json()
    assert review_session["total"] == 1
    assert review_session["session_type"] == "review"
    state = c.get(f"/api/sessions/{review_session['session_id']}").json()
    assert state["current_question_id"] == qid


def test_statistics_endpoint_shapes(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    c.post(f"/api/sessions/{sid}/answer",
           json={"question_id": qid, "chosen_answer": "B"})
    c.post(f"/api/sessions/{sid}/skip", json={})
    stats = c.get("/api/statistics/s1").json()
    assert stats["totals"]["answered"] == 1
    assert stats["totals"]["skipped"] == 1
    assert stats["totals"]["accuracy"] == 1.0   # skips never distort accuracy
    assert stats["by_subject"]["maths"]["attempted"] == 1
    assert stats["review"]["total"] == 1        # skip created a review item
    assert len(stats["practice_volume"]) == 14
    assert "weak_topics" in stats and "topic_mastery" in stats

    system = c.get("/api/system/statistics").json()
    assert system["questions_total"] == 1
    assert system["validation_status_counts"]["approved"] == 1
    assert system["hardest_questions"][0]["error_rate"] == 0.0


def test_recommendations_endpoint(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    c.post(f"/api/sessions/{sid}/answer",
           json={"question_id": qid, "chosen_answer": "A"})
    empty = c.get("/api/recommendations/s1").json()
    assert empty["recommendations"] == []   # nothing due, no weakness yet
    built = c.get("/api/recommendations/s1",
                  params={"refresh": "true"}).json()
    assert built["recommendations"]
    assert built["recommendations"][0]["kind"] in {
        "review", "practice", "learn", "catch_up"}
    assert c.get("/api/recommendations/s1").json()["recommendations"]


def test_loop_endpoint_covers_all_steps(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    for _ in range(3):
        c.post(f"/api/sessions/{sid}/answer",
               json={"question_id": qid, "chosen_answer": "A",
                     "action": "retry"})
    loop = c.get("/api/loop/s1").json()
    assert loop["loop"] == ["learn", "practise", "assess", "identify_error",
                            "explain", "review", "re_practise",
                            "update_mastery"]
    assert loop["practise"]["question_ids"] == [qid]
    assert loop["identify_error"]["repeated_mistakes"][0]["question_id"] == qid
    assert loop["explain"][0]["question_id"] == qid
    assert loop["update_mastery"]["topic_mastery"][0]["topic"] == \
        "maths-arithmetic"
    assert loop["recommended_activities"]


def test_progress_endpoint_extends_existing_shape(client):
    c, qid = client
    sid = c.post("/api/sessions/start", json={"student_id": "s1"}).json()[
        "session_id"]
    c.post(f"/api/sessions/{sid}/answer",
           json={"question_id": qid, "chosen_answer": "A"})
    prog = c.get("/api/progress/s1").json()
    assert prog["weak_topics"] == []   # one attempt is not enough evidence
    assert prog["review"]["total"] == 1
    assert prog["recommendations"] == []
    parent = c.get("/api/parent/s1").json()
    assert parent["practice_completed"] == 1
    assert parent["weekly_activity"]["days"]
    assert "mock_results" in parent and "review_completion" in parent
    assert parent["recommended_next_steps"]
