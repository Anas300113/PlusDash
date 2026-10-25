"""Student ownership-boundary regression tests (P1-13).

Reproduce the concrete defect: every per-student route takes a bare
``student_id`` (path or body) and no endpoint verified the caller owns the
requested resource. Before the fix, ANY caller who knew another student's id
could read that student's progress / reviews / loop / parent dashboard, resume
their session, or submit answers into their session -- an ownership hole, not
just a privacy nicety.

The boundary is opt-in strict mode (``PLUS_REQUIRE_STUDENT_IDENTITY``): when
enabled a caller must present ``X-Student-Id`` and it must equal the OWNING
student id (for session routes the owner is read from the stored session, not
the URL). When disabled the API behaves exactly as before, so the stateless
demo UI and existing frozen tests keep working. These tests assert BOTH the
protected behaviour (flag on) and the unchanged behaviour (flag off), and they
drive the real persistence + TestClient path, never a mock.
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
def env(tmp_path, monkeypatch):
    """A client bound to a fresh DB with one approved question."""
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text="2+2?", correct_answer="B",
        explanation="Because 2+2=4.",
        options_json=[{"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}])
    s.add(q)
    s.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    s.commit()
    qid = q.id
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app), qid


def _strict(monkeypatch):
    monkeypatch.setenv("PLUS_REQUIRE_STUDENT_IDENTITY", "1")


# ---- per-student GET endpoints ------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/progress/s1",
    "/api/statistics/s1",
    "/api/reviews/s1",
    "/api/recommendations/s1",
    "/api/loop/s1",
    "/api/parent/s1",
])
def test_cross_student_read_is_blocked(env, monkeypatch, path):
    """Under strict identity a *mismatched* header and a *missing* header are
    rejected. NOTE: this does NOT prove ownership -- a caller who echoes the
    victim's own id still passes (see
    ``test_supplying_victim_identifier_alone_is_NOT_prevented``). This test only
    pins the guard's reject-mismatch / require-present behaviour."""
    c, _ = env
    _strict(monkeypatch)
    r = c.get(path, headers={"X-Student-Id": "attacker"})
    assert r.status_code == 403, path
    r = c.get(path)
    assert r.status_code == 401, path
    r = c.get(path, headers={"X-Student-Id": "s1"})
    assert r.status_code == 200, path


@pytest.mark.parametrize("path", [
    "/api/progress/s1",
    "/api/reviews/s1",
    "/api/parent/s1",
])
def test_default_off_preserves_previous_behaviour(env, monkeypatch, path):
    """With the flag OFF (default) the endpoint works with no header, so the
    frozen suite and the stateless demo UI are unaffected."""
    c, _ = env
    monkeypatch.delenv("PLUS_REQUIRE_STUDENT_IDENTITY", raising=False)
    r = c.get(path)
    assert r.status_code == 200, path


# ---- session-scoped endpoints -------------------------------------------

def test_cannot_read_or_act_on_another_students_session(env, monkeypatch):
    """Resume/results/answer/complete/abandon must not let one student touch
    another's session, even knowing its id."""
    c, qid = env
    _strict(monkeypatch)
    sid = c.post("/api/sessions/start", headers={"X-Student-Id": "s1"},
                 json={"student_id": "s1"}).json()["session_id"]
    assert c.get(f"/api/sessions/{sid}",
                 headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.get(f"/api/sessions/{sid}/results",
                 headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.post(f"/api/sessions/{sid}/answer",
                  headers={"X-Student-Id": "attacker"},
                  json={"question_id": qid, "chosen_answer": "B"}
                  ).status_code == 403
    assert c.post(f"/api/sessions/{sid}/complete",
                  headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.post(f"/api/sessions/{sid}/abandon",
                  headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.get(f"/api/sessions/{sid}",
                 headers={"X-Student-Id": "s1"}).status_code == 200


def test_attempts_endpoint_requires_matching_identity(env, monkeypatch):
    """Legacy POST /api/attempts must also refuse a mismatched X-Student-Id."""
    c, qid = env
    _strict(monkeypatch)
    sid = c.post("/api/sessions/start", headers={"X-Student-Id": "s1"},
                 json={"student_id": "s1"}).json()["session_id"]
    r = c.post("/api/attempts", headers={"X-Student-Id": "attacker"},
               json={"student_id": "s1", "session_id": sid,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 403
    r = c.post("/api/attempts", headers={"X-Student-Id": "s1"},
               json={"student_id": "s1", "session_id": sid,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 200 and r.json()["is_correct"] is True


# ---- DOCUMENTED, UNRESOLVED security limitation (P0-5) -------------------
# The ``PLUS_REQUIRE_STUDENT_IDENTITY`` guard compares a caller-supplied
# ``X-Student-Id`` header against a caller-supplied ``student_id`` (URL path or
# body). A caller-supplied identifier is NOT proof of identity: an attacker who
# knows (or guesses) the victim's student id sets the header to that same id and
# the request is accepted. These tests assert the CURRENT behaviour explicitly
# so the gap is visible and cannot be mistaken for verified ownership.
#
# This is NOT a passing security guarantee. The platform has no login/session/
# token identity for students, so there is no server-trusted principal from
# which to derive ownership. RESOLUTION (out of scope to invent here): add a
# real authentication mechanism (e.g. signed session cookie or bearer token
# issued at login), derive the student id from that server-verified principal,
# and ignore any caller-supplied student id. Until then, student-specific and
# parent data MUST be treated as world-readable to anyone who knows an id, and
# the platform must NOT be represented as production-secure.
def test_supplying_victim_identifier_alone_is_NOT_prevented(env, monkeypatch):
    """KNOWN GAP (not a security guarantee): even with strict identity ON, a
    caller who supplies the victim's own student id in BOTH the header and the
    URL is served that student's data. The guard only rejects a *mismatched*
    header, which an attacker trivially satisfies by echoing the victim's id.
    """
    c, _ = env
    _strict(monkeypatch)
    for path in ("/api/progress/s1", "/api/parent/s1", "/api/reviews/s1"):
        r = c.get(path, headers={"X-Student-Id": "s1"})
        assert r.status_code == 200, (
            f"{path}: expected the documented gap (attacker echoing victim id "
            f"is accepted); got {r.status_code}. If this now returns 403, the "
            f"ownership boundary has been genuinely implemented -- update this "
            f"test to assert protection and remove this notice.")


def test_parent_access_by_arbitrary_student_id_is_NOT_prevented(env, monkeypatch):
    """KNOWN GAP: the parent dashboard endpoint takes a bare student id with no
    parent-identity binding, so any caller who knows a student id can read that
    student's parent-facing summary. Documented, unresolved, same root cause as
    the student-ownership gap (no server-trusted identity)."""
    c, _ = env
    _strict(monkeypatch)
    # A 'parent' who only knows the student's id -- no parent credential exists.
    r = c.get("/api/parent/s1", headers={"X-Student-Id": "s1"})
    assert r.status_code == 200, "documented gap: parent data readable by id"




# ---- Foundation gate: session CREATION ownership (write path) -------------
def test_creating_a_session_for_another_student_is_blocked(env, monkeypatch):
    """Foundation gate P1: under strict identity, a caller must not be able to
    create sessions ATTRIBUTED to another student by substituting the
    identifier. Both session-creation route styles are covered. Before the
    fix these two routes had no ownership guard at all (the session-scoped
    routes were already guarded, so an attacker could not then answer inside
    the planted session -- but the planted session still polluted the victim's
    learning record)."""
    c, _ = env
    _strict(monkeypatch)
    # body-based route: mismatched header -> 403; missing header -> 401
    r = c.post("/api/sessions/start", json={"student_id": "victim"},
               headers={"X-Student-Id": "attacker"})
    assert r.status_code == 403
    r = c.post("/api/sessions/start", json={"student_id": "victim"})
    assert r.status_code == 401
    # query-param route: same boundary
    r = c.post("/api/sessions?student_id=victim",
               headers={"X-Student-Id": "attacker"})
    assert r.status_code == 403
    r = c.post("/api/sessions?student_id=victim")
    assert r.status_code == 401
    # positive control: a student can still start their OWN session
    r = c.post("/api/sessions/start", json={"student_id": "me"},
               headers={"X-Student-Id": "me"})
    assert r.status_code == 200 and r.json()["session_id"]



# ---- Real-data mode: fail closed (P0-5 Phase 1) ----------------------------
# PLUS_REAL_STUDENT_DATA declares "this deployment holds real student data".
# Because no server-verified student identity exists, student-scoped routes
# must then refuse (503) rather than serve data behind the spoofable
# X-Student-Id header. This mirrors require_reviewer's fail-closed 503. It does
# NOT authenticate; it makes the absence of authentication loud.

def _real(monkeypatch):
    monkeypatch.setenv("PLUS_REAL_STUDENT_DATA", "1")


@pytest.mark.parametrize("path", [
    "/api/progress/s1",
    "/api/statistics/s1",
    "/api/reviews/s1",
    "/api/recommendations/s1",
    "/api/loop/s1",
    "/api/parent/s1",
])
def test_real_data_mode_locks_student_reads(env, monkeypatch, path):
    """In real-data mode a student-scoped GET is refused with 503 -- even when
    the caller supplies a matching X-Student-Id, because that header proves
    nothing."""
    c, _ = env
    _real(monkeypatch)
    r = c.get(path, headers={"X-Student-Id": "s1"})
    assert r.status_code == 503, path
    # Also refused with no header at all (fail closed, not fail open).
    assert c.get(path).status_code == 503, path


def test_real_data_mode_locks_session_scoped_routes(env, monkeypatch):
    """Session-scoped routes are locked too: create a session with the flag
    OFF, then flip to real-data mode and confirm state/answer are refused."""
    c, _ = env
    sid = c.post("/api/sessions/start",
                 json={"student_id": "s1"}).json()["session_id"]
    _real(monkeypatch)
    assert c.get(f"/api/sessions/{sid}",
                 headers={"X-Student-Id": "s1"}).status_code == 503
    assert c.post(f"/api/sessions/{sid}/answer",
                  headers={"X-Student-Id": "s1"},
                  json={"student_id": "s1", "session_id": sid,
                        "question_id": "q", "chosen_answer": "B"}
                  ).status_code == 503


def test_real_data_mode_locks_attempts_write(env, monkeypatch):
    """The attempts write path is locked in real-data mode."""
    c, qid = env
    sid = c.post("/api/sessions/start",
                 json={"student_id": "s1"}).json()["session_id"]
    _real(monkeypatch)
    r = c.post("/api/attempts", headers={"X-Student-Id": "s1"},
               json={"student_id": "s1", "session_id": sid,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 503


def test_real_data_mode_is_independent_of_identity_flag(env, monkeypatch):
    """Real-data mode locks routes even when PLUS_REQUIRE_STUDENT_IDENTITY is
    OFF -- it is a separate, stronger control."""
    c, _ = env
    monkeypatch.delenv("PLUS_REQUIRE_STUDENT_IDENTITY", raising=False)
    _real(monkeypatch)
    assert c.get("/api/progress/s1").status_code == 503


def test_real_data_mode_fails_closed_by_default(env, monkeypatch):
    """An unset real-data mode defaults to the secure production behavior."""
    c, _ = env
    monkeypatch.delenv("PLUS_REAL_STUDENT_DATA", raising=False)
    assert c.get("/api/progress/s1").status_code == 503
    assert c.get("/api/parent/s1").status_code == 503
