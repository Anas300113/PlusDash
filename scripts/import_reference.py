"""Bulk import reference banks through adapters.
Each file becomes a SourceDocument (rights=licensed, MIT); each
record becomes a CanonicalQuestion + QuestionOccurrence + review row
(status=validation_required). Fingerprint dedup is global."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path

from src.canonical.validators import validate_canonical_question
from src.core.database import (
    CanonicalQuestion, CorpusSnapshot, PipelineRun, QuestionOccurrence,
    QuestionRegionBoard, QuestionReviewStatus, SourceDocument,
    get_engine, get_session_factory, init_db, utcnow,
)
from src.core.hashing import content_fingerprint, sha256_file
from src.core.logging import get_logger
from src.source.adapters.prep_adapter import PrepAdapter
from src.source.adapters.tutor_adapter import TutorAdapter

log = get_logger("import_reference")


def _doc_for(session, repo_name: str, repo_url: str, path: Path, batch: str,
             source_sha: str = "", licence_note: str = "") -> tuple:
    """Return (SourceDocument, upstream_changed).

    The document row records the source file hash, the audited source commit
    and the licence/attribution notice so every imported question is traceable
    to an exact upstream version. If the upstream FILE has changed since the
    first import, the change is detected and reported but the existing row --
    and everything imported from it -- is never silently overwritten.
    """
    sha = sha256_file(path)
    doc = (session.query(SourceDocument)
           .filter_by(repo_name=repo_name, source_path=path.name).first())
    if doc is None:
        doc = SourceDocument(id=str(uuid.uuid4()), repo_name=repo_name,
                             repo_url=repo_url, source_path=path.name,
                             file_sha256=sha, file_size=path.stat().st_size,
                             file_type="json", commit_sha=source_sha,
                             rights_status="licensed",
                             rights_note=licence_note
                             or "MIT-licensed reference bank",
                             ingestion_batch=batch)
        session.add(doc)
        session.commit()
        return doc, False
    if doc.file_sha256 and doc.file_sha256 != sha:
        log.warning(
            "upstream change detected for %s (recorded %s..., current %s...); "
            "existing import kept, nothing overwritten", path.name,
            doc.file_sha256[:12], sha[:12])
        return doc, True
    return doc, False


def import_file(session, path: Path, adapter, repo_name: str, repo_url: str,
                batch: str, source_sha: str = "", run_id: str | None = None
                ) -> dict:
    doc, changed = _doc_for(session, repo_name, repo_url, path, batch,
                            source_sha, adapter.licence_note)
    records = json.loads(path.read_text(encoding="utf-8"))
    stats = {"total": len(records), "imported": 0, "invalid": 0, "dupes": 0,
             "upstream_changed": changed, "document_id": doc.id,
             "sha256": doc.file_sha256}
    for ext in records:
        canon = adapter.to_canonical(ext)
        result = validate_canonical_question(canon)
        if not result.passed:
            stats["invalid"] += 1
            continue
        fp = content_fingerprint(canon.get("question_text", ""),
                                 canon.get("correct_answer", ""))
        if session.query(CanonicalQuestion).filter_by(fingerprint=fp).first():
            stats["dupes"] += 1
            continue
        q = CanonicalQuestion(
            id=str(uuid.uuid4()), subject=canon["subject"],
            topic=canon.get("topic", "general"),
            subtopic=canon.get("subtopic", ""),
            question_type=canon.get("question_type", "mcq"),
            difficulty=canon.get("difficulty"),
            question_text=canon.get("question_text", ""),
            context=canon.get("context", ""),
            correct_answer=canon.get("correct_answer", ""),
            options_json=canon.get("options_json"),
            explanation=canon.get("explanation", ""),
            worked_solution=canon.get("worked_solution", ""),
            hint=canon.get("hint", ""),
            exam_board=canon.get("exam_board", ""),
            region=canon.get("region", ""),
            fingerprint=fp)
        session.add(q)
        session.flush()
        session.add(QuestionOccurrence(
            id=str(uuid.uuid4()), canonical_question_id=q.id,
            document_id=doc.id, page_id="",
            question_number=canon.get("source_question_id", ""),
            extraction_run=batch, extraction_version="adapter-0.2.0",
            extraction_confidence=0.8))
        session.add(QuestionReviewStatus(
            question_id=q.id, status="validation_required",
            source=f"adapter:{repo_name}", confidence=0.8))
        # ---- Gate 2: preserve source region/board assertion ----
        reg = canon.get("region") or ""
        brd = canon.get("exam_board") or ""
        if brd == "mixed":
            brd = ""
        session.add(QuestionRegionBoard(
            id=str(uuid.uuid4()), question_id=q.id, region=reg, board=brd,
            source_document_id=doc.id,
            source_question_id=canon.get("source_question_id", ""),
            confidence=0.8, ingestion_batch=batch))
        # ---- end Gate 2 ----
        stats["imported"] += 1
    session.commit()
    log.info("imported %s: %s", path.name, stats)
    return stats


def import_banks(session, bank_dir: Path, adapter, repo_name: str,
                 repo_url: str, batch: str, source_sha: str = "",
                 run_id: str | None = None) -> dict:
    """Deterministic multi-file bank import (Gate 1).

    Records are grouped into content-fingerprint CLUSTERS across all files
    before anything is written, so the result never depends on file iteration
    order:

    * one canonical question per cluster; content comes from the cluster
      representative = min (filename, source question id);
    * every source record keeps its own QuestionOccurrence (document +
      source question id), including duplicate records sharing a canonical,
      so no legitimate source association is dropped;
    * canonical region/board = the single distinct non-empty assertion among
      cluster members, or "" when members assert conflicting values (never
      invented, never silently resolved); every source assertion is preserved
      in question_region_board (Gate 2);
    * existing canonical rows are NEVER overwritten; divergences are returned
      in ``conflicts`` for review;
    * repeat runs add only missing occurrences (idempotent) and never touch
      existing review-status rows.
    """
    files = sorted(bank_dir.glob("*.json"))
    clusters: dict[str, list] = {}
    per_file: dict[str, dict] = {}
    invalid = 0
    for path in files:
        records = json.loads(path.read_text(encoding="utf-8"))
        doc, changed = _doc_for(session, repo_name, repo_url, path, batch,
                                source_sha, adapter.licence_note)
        per_file[path.name] = {
            "records": len(records), "sha256": doc.file_sha256,
            "document_id": doc.id, "upstream_changed": changed}
        for ext in records:
            canon = adapter.to_canonical(ext)
            if not validate_canonical_question(canon).passed:
                invalid += 1
                continue
            fp = content_fingerprint(canon["question_text"],
                                     canon["correct_answer"])
            clusters.setdefault(fp, []).append(
                {"canon": canon, "filename": path.name, "doc": doc,
                 "changed": changed, "source_id": str(ext.get("id", ""))})
    return _write_clusters(session, clusters, per_file, invalid, adapter,
                           batch, run_id)


def _write_clusters(session, clusters: dict, per_file: dict, invalid: int,
                    adapter, batch: str, run_id: str | None = None) -> dict:
    stats = {"files": len(per_file),
             "records": sum(f["records"] for f in per_file.values()),
             "imported": 0, "invalid": invalid, "occurrences_added": 0,
             "duplicates_merged": 0, "region_set_from_duplicate": 0,
             "region_ambiguous": 0, "board_conflicts": 0,
             "upstream_changed": 0,
             "conflicts": [], "per_file": per_file,
             "manifest_files": []}
    for fp, members in clusters.items():
        members.sort(key=lambda m: (m["filename"], m["source_id"]))
        rep = members[0]
        stats["duplicates_merged"] += len(members) - 1
        stats["upstream_changed"] += 1 if any(
            m["changed"] for m in members) else 0

        # ---- Gate 2: preserve every source assertion, never collapse ----
        regions = {m["canon"]["region"] for m in members
                   if m["canon"].get("region")}
        boards = {m["canon"]["exam_board"] for m in members
                  if m["canon"].get("exam_board")
                  and m["canon"]["exam_board"] != "mixed"}
        region = regions.pop() if len(regions) == 1 else ""
        board = list(boards)[0] if len(boards) == 1 else ""
        if len(regions) > 1:
            stats["region_ambiguous"] += 1
        if len(boards) > 1:
            stats["board_conflicts"] += 1

        q = session.query(CanonicalQuestion).filter_by(
            fingerprint=fp).first()
        if q is None:
            q = CanonicalQuestion(
                id=str(uuid.uuid4()), subject=rep["canon"]["subject"],
                topic=rep["canon"].get("topic", "general"),
                subtopic=rep["canon"].get("subtopic", ""),
                question_type=rep["canon"].get("question_type", "mcq"),
                difficulty=rep["canon"].get("difficulty"),
                question_text=rep["canon"].get("question_text", ""),
                context=rep["canon"].get("context", ""),
                correct_answer=rep["canon"].get("correct_answer", ""),
                options_json=rep["canon"].get("options_json"),
                explanation=rep["canon"].get("explanation", ""),
                exam_board=board, region=region, fingerprint=fp)
            session.add(q)
            session.flush()
            session.add(QuestionReviewStatus(
                question_id=q.id, status="validation_required",
                source=f"adapter:{adapter.source_name}", confidence=0.8))
            stats["imported"] += 1
        else:
            # Existing canonical row: detect divergence between stored
            # consensus and what this batch asserts, but never overwrite.
            if ((q.region or "") != region or (q.exam_board or "") != board):
                stats["conflicts"].append({
                    "fingerprint": fp, "existing_region": q.region,
                    "existing_board": q.exam_board,
                    "deterministic_region": region,
                    "deterministic_board": board,
                    "sources": [f"{m['filename']}#{m['source_id']}"
                                for m in members]})

        # Persist each source record's region/board assertion individually.
        for m in members:
            reg = m["canon"].get("region") or ""
            brd = m["canon"].get("exam_board") or ""
            if brd == "mixed":
                brd = ""
            already_rb = (session.query(QuestionRegionBoard)
                          .filter_by(question_id=q.id,
                                     source_document_id=m["doc"].id,
                                     source_question_id=m["source_id"])
                          .first())
            if already_rb is None:
                session.add(QuestionRegionBoard(
                    id=str(uuid.uuid4()), question_id=q.id,
                    region=reg, board=brd,
                    source_document_id=m["doc"].id,
                    source_question_id=m["source_id"],
                    confidence=0.8, ingestion_batch=batch))
        # ---- end Gate 2 ----

        for m in members:
            exists = session.query(QuestionOccurrence).filter_by(
                document_id=m["doc"].id,
                question_number=m["source_id"]).first()
            if exists is None:
                session.add(QuestionOccurrence(
                    id=str(uuid.uuid4()), canonical_question_id=q.id,
                    document_id=m["doc"].id, page_id="",
                    question_number=m["source_id"],
                    extraction_run=batch,
                    extraction_version="adapter-0.2.0",
                    extraction_confidence=0.8))
                stats["occurrences_added"] += 1
    session.commit()
    for name, info in per_file.items():
        stats["manifest_files"].append({"file": name, **info})
    log.info("bank import: %s", {k: v for k, v in stats.items()
                                 if k not in ("manifest_files", "per_file",
                                              "conflicts")})
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Import reference banks via adapters")
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--tutor-json", default=None)
    ap.add_argument("--prep-dir", default=None)
    ap.add_argument("--batch", default="ref-001")
    ap.add_argument("--source-sha", default="",
                    help="audited upstream commit SHA recorded on each "
                         "SourceDocument for traceability")
    ap.add_argument("--manifest-dir", default=None,
                    help="write a per-repo JSON ingestion manifest here")
    args = ap.parse_args()
    engine = get_engine(args.db)
    init_db(engine)
    session = get_session_factory(engine)()

    # ---- Gate 3: immutable per-run record ----
    run_id = str(uuid.uuid4())
    run = PipelineRun(
        id=run_id, pipeline_version="adapter-0.2.0", status="running",
        started_at=utcnow())
    session.add(run)
    session.commit()

    total = {}
    manifests: dict[str, dict] = {}
    if args.tutor_json:
        total["tutor"] = import_file(
            session, Path(args.tutor_json), TutorAdapter(),
            "11plus-tutor", "https://github.com/jhammant/11plus-tutor",
            args.batch, args.source_sha, run_id)
    if args.prep_dir:
        result = import_banks(
            session, Path(args.prep_dir), PrepAdapter(), "11plus-prep",
            "https://github.com/SahirVhora/11plus-prep", args.batch,
            args.source_sha, run_id)
        manifests["11plus-prep"] = result
        total["prep"] = result

    # ---- Gate 3: cumulative corpus snapshot ----
    _write_corpus_snapshot(session, run_id)
    run.status = "completed"
    run.completed_at = utcnow()
    run.stats_json = total
    session.commit()

    if args.manifest_dir and manifests:
        _write_manifests(Path(args.manifest_dir), manifests, args, run_id)
        signing_key = _manifest_signing_key()
        source_repos = [
            {
                "name": repo,
                "repo_url": ("https://github.com/SahirVhora/11plus-prep"
                             if repo == "11plus-prep" else repo),
                "commit_sha": args.source_sha,
                "licence": ("MIT License, Copyright (c) 2026 Sahir Vhora"
                            if repo == "11plus-prep"
                            else "see source repository"),
                "rights_note": ("MIT License, Copyright (c) 2026 Sahir Vhora"
                                if repo == "11plus-prep"
                                else "see source repository"),
                "batch": args.batch,
            }
            for repo in manifests
        ]
        _write_licence_manifest(Path(args.manifest_dir), source_repos,
                                run_id, signing_key)
    print(total)


def _write_corpus_snapshot(session, run_id: str) -> None:
    """Gate 3: cumulative corpus snapshot after each ingestion run.

    Records whole-corpus state (total questions, occurrences, approved
    counts, per-source breakdown) so incremental runs can reconcile against
    the full corpus rather than only the delta of this run.
    """
    from sqlalchemy import func
    total_questions = session.query(func.count(CanonicalQuestion.id)).scalar() or 0
    total_occurrences = (session.query(func.count(QuestionOccurrence.id))
                         .scalar() or 0)
    total_approved = (session.query(func.count(QuestionReviewStatus.question_id))
                      .filter(QuestionReviewStatus.status == "approved")
                      .scalar() or 0)
    total_pending = (session.query(func.count(QuestionReviewStatus.question_id))
                     .filter(QuestionReviewStatus.status != "approved")
                     .scalar() or 0)

    per_source: dict[str, dict] = {}
    rows = (session.query(
        SourceDocument.repo_name,
        func.count(CanonicalQuestion.id).label("q_count"),
        func.count(QuestionOccurrence.id).label("occ_count"))
            .outerjoin(QuestionOccurrence,
                       QuestionOccurrence.document_id == SourceDocument.id)
            .outerjoin(CanonicalQuestion,
                       CanonicalQuestion.id == QuestionOccurrence.canonical_question_id)
            .group_by(SourceDocument.repo_name).all())
    for repo, q_count, occ_count in rows:
        per_source[repo or "unknown"] = {
            "questions": q_count or 0,
            "occurrences": occ_count or 0,
        }

    snapshot = CorpusSnapshot(
        id=str(uuid.uuid4()), snapshot_at=utcnow(),
        total_questions=total_questions,
        total_occurrences=total_occurrences,
        total_approved=total_approved,
        total_pending_review=total_pending,
        per_source_json=per_source, run_id=run_id)
    session.add(snapshot)
    session.commit()


def _write_manifests(manifest_dir: Path, manifests: dict, args,
                     run_id: str | None = None) -> None:
    """Reproducible per-repo ingestion manifest (source URL/SHA, licence,
    per-file hashes and outcomes, duplicate/attribution statistics). Each
    run writes an immutable file named with run_id so prior manifests are
    never overwritten (Gate 3). Manifests are HMAC-signed when
    PLUS_MANIFEST_SIGNING_KEY is set (P2 hygiene).
    """
    signing_key = _manifest_signing_key()
    manifest_dir.mkdir(parents=True, exist_ok=True)
    for repo, result in manifests.items():
        sha_tag = (args.source_sha or "unversioned")[:12]
        run_tag = (run_id or "unknown")[:8]
        name = f"{repo}-{sha_tag}-{run_tag}.json"
        totals = {
            "files": result["files"],
            "records": result["records"],
            "imported": result["imported"],
            "invalid": result["invalid"],
            "duplicates_merged": result["duplicates_merged"],
            "occurrences_added": result["occurrences_added"],
            "region_set_from_duplicate":
                result["region_set_from_duplicate"],
            "region_ambiguous": result["region_ambiguous"],
            "board_conflicts": result.get("board_conflicts", 0),
            "region_conflicts_kept_for_review": len(
                result.get("conflicts", [])),
            "upstream_changed_files": result["upstream_changed"],
        }
        payload = {
            "source_repo": ("https://github.com/SahirVhora/11plus-prep"
                            if repo == "11plus-prep" else repo),
            "source_sha": args.source_sha,
            "licence": ("MIT License, Copyright (c) 2026 Sahir Vhora"
                        if repo == "11plus-prep" else "see source repository"),
            "import_batch": args.batch,
            "run_id": run_id,
            "imported_at_utc": datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds"),
            "totals": totals,
            "files": result.get("manifest_files", []),
            "attribution_conflicts": result.get("conflicts", []),
        }
        signature = sign_manifest(payload, signing_key)
        if signature:
            payload["signature"] = signature
        out = manifest_dir / name
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("manifest written: %s", out)


def _manifest_signing_key() -> str | None:
    """Return the manifest signing key from the environment, if configured.

    Set ``PLUS_MANIFEST_SIGNING_KEY`` to enable HMAC-SHA256 signatures on
    every written manifest. Without it, manifests are written unsigned
    (signature field omitted).
    """
    return os.environ.get("PLUS_MANIFEST_SIGNING_KEY", "") or None


def sign_manifest(payload: dict, signing_key: str | None = None) -> str:
    """Return an HMAC-SHA256 hex signature for a manifest payload.

    The signature is computed over the canonical JSON serialization of the
    payload (keys sorted, no whitespace) so it is reproducible and covers
    every field including ``run_id`` and ``imported_at_utc``. Returns the
    empty string when no signing key is configured.
    """
    if not signing_key:
        signing_key = _manifest_signing_key()
    if not signing_key:
        return ""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        signing_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_manifest(manifest_path: Path | str,
                    signing_key: str | None = None) -> bool:
    """Verify a manifest file's HMAC-SHA256 signature.

    Returns ``True`` when the file contains a valid ``signature`` field that
    matches a recomputed signature over the rest of the payload. Returns
    ``False`` when the file is missing, unparseable, has no signature, or the
    signature does not match. When no signing key is configured, any
    signature present is treated as valid (unsigned manifests accepted).
    """
    if not signing_key:
        signing_key = _manifest_signing_key()
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    signature = data.pop("signature", None)
    if not signature:
        # No signature field: valid only when signing is not required.
        return signing_key is None
    expected = sign_manifest(data, signing_key)
    return hmac.compare_digest(signature, expected)


def _write_licence_manifest(manifest_dir: Path, source_repos: list[dict],
                            run_id: str | None = None,
                            signing_key: str | None = None) -> None:
    """Write a dependency/licence manifest per source repo.

    Each entry records the source repository name, URL, audited commit SHA,
    declared licence, and rights note, plus the Plus project's own Python
    dependencies (from ``pyproject.toml``) so auditors can see exactly what
    code and licences were in play for each ingested source.
    """
    manifest_dir.mkdir(parents=True, exist_ok=True)
    # Read project dependencies from pyproject.toml (no external deps).
    project_deps: list[str] = []
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        in_deps = False
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "dependencies = [":
                in_deps = True
                continue
            if in_deps:
                if stripped == "]":
                    break
                if stripped.startswith('"') or stripped.startswith("'"):
                    dep = stripped.strip('"').strip("'").rstrip(",")
                    project_deps.append(dep)

    run_tag = (run_id or "unknown")[:8]
    for repo in source_repos:
        payload = {
            "source_repo": repo.get("name", repo.get("repo_name", "")),
            "source_url": repo.get("repo_url", ""),
            "source_commit_sha": repo.get("commit_sha", ""),
            "licence": repo.get("licence", ""),
            "rights_note": repo.get("rights_note", ""),
            "import_batch": repo.get("batch", ""),
            "run_id": run_id,
            "generated_at_utc": datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds"),
            "project_dependencies": project_deps,
            "project_license": "MIT",
        }
        signature = sign_manifest(dict(payload), signing_key)
        if signature:
            payload["signature"] = signature
        sha_tag = (repo.get("commit_sha", "") or "unversioned")[:12]
        name = (
            f"licence-manifest-{repo.get('name', repo.get('repo_name', 'unknown'))}"
            f"-{sha_tag}-{run_tag}.json"
        )
        out = manifest_dir / name
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("licence manifest written: %s", out)


if __name__ == "__main__":
    main()
