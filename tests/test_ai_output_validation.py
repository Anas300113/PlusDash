"""AI output validation tests: schema + provenance recorded, nothing auto-publishes."""
from __future__ import annotations

import uuid

from src.core.database import AIApproval, AIJob, AIOutput, AIValidation


def test_ai_provenance_chain(session):
    job = AIJob(id=str(uuid.uuid4()), job_type="generator", source_input="gap: fractions",
                model="test-model", model_version="v1", prompt_version="p1", status="completed")
    session.add(job)
    session.commit()
    out = AIOutput(id=str(uuid.uuid4()), job_id=job.id, output_type="generated_question",
                   confidence=0.7, output_json={"question_text": "1+1?", "correct_answer": "2"})
    session.add(out)
    session.commit()
    session.add(AIValidation(id=str(uuid.uuid4()), ai_output_id=out.id,
                             validator_type="schema", passed=True,
                             details_json={"checks": ["required-fields"]}))
    session.add(AIApproval(id=str(uuid.uuid4()), ai_output_id=out.id,
                           status="pending", reviewer_id="", comments=""))
    session.commit()
    assert session.query(AIApproval).filter_by(status="pending").count() == 1
    # provenance queryable end-to-end
    ap = session.query(AIApproval).first()
    o = session.query(AIOutput).filter_by(id=ap.ai_output_id).first()
    j = session.query(AIJob).filter_by(id=o.job_id).first()
    assert (j.model, j.prompt_version) == ("test-model", "p1")
