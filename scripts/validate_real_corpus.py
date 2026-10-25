"""Controlled real-corpus validation harness.

Re-runs the full ingestion pipeline over the fixed 21-file 11+ sample
(21 non-zip source files + 2 ZIP archives) that is the accepted validation
baseline, and prints the measured metrics used for the before/after
comparison in VALIDATION_REPORT.md:

* MCQ option extraction (occurrences, option sets, canonical retention)
* answer linking (links, own-document key support, false positives)
* OCR (required/attempted/success/empty)
* provenance (canonical -> occurrence -> page -> document)
* assets on disk
* second-run idempotency

The harness is deterministic: same sample + same code -> same counts.
It never infers answers and never manufactures options.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The accepted baseline sample: 21 non-zip source files + 2 ZIP archives.
# (name, category) — categories match VALIDATION_REPORT.md section 2.
SAMPLE_FILES = [
    ("Maths_2.pdf", "native_text_pdf"),
    ("English_2.pdf", "native_text_pdf"),
    ("9+ Maths Sample Paper 2D.pdf", "mixed_image_heavy"),
    ("9+ Sample papers 2013 2.pdf", "mixed_image_heavy"),
    ("English_3.pdf", "native_text_pdf"),
    ("Maths_P9.pdf", "native_text_pdf"),
    ("English_AS4-6.pdf", "native_text_pdf"),
    ("11ComprehensionPracticePaper.pdf", "native_text_pdf"),
    ("11MathsPracticePaper2.pdf", "native_text_pdf"),
    ("Maths_3.pdf", "native_text_pdf"),
    ("csse 2008 MATHS marking scheme.pdf", "answer_key"),
    ("CGP11+EnglishAnswerSheet.pdf", "answer_key"),
    ("2008 intake maths.pdf", "scanned_pdf"),
    ("2008 intake English.pdf", "scanned_pdf"),
    ("11VerbalReasoning.pdf", "scanned_pdf"),
    ("11VerbalPaper2.pdf", "scanned_pdf"),
    ("CSSE_Maths_2007.pdf", "scanned_pdf"),
    ("CSSE_English_2007.pdf", "scanned_pdf"),
    ("CSSE_Maths_2008_Ans.pdf", "scanned_pdf"),
    ("11NVRPaper2.pdf", "nvr"),
    ("11_Sample_ maths_exam_questions.pptx", "pptx"),
    ("susan daughtrey vr techniques.zip", "zip"),
    ("core-skills-booster-worksheets-pack-2-2.zip", "zip"),
]

TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

REPO_NAME = "11-dump"
PIPELINE_VERSION = "validate-1.0.0"


def configure_tesseract() -> str:
    """Point pytesseract at an installed Tesseract if it is not on PATH."""
    try:
        import pytesseract
    except Exception:
        return ""
    try:
        pytesseract.get_tesseract_version()
        return str(pytesseract.pytesseract.tesseract_cmd)
    except Exception:
        pass
    for candidate in TESSERACT_CANDIDATES:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return ""


def build_sample(corpus_root: Path, dest: Path) -> list[str]:
    """Copy the fixed sample files into a flat directory (idempotent)."""
    dest.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for name, _category in SAMPLE_FILES:
        target = dest / name
        if target.exists():
            continue
        matches = sorted(corpus_root.rglob(name))
        if not matches:
            missing.append(name)
            continue
        target.write_bytes(matches[0].read_bytes())
    return missing


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _counts(session) -> dict:
    """Table counts. JSON `null` is falsy in Python but not SQL NULL, so
    option counts are computed in Python, never with `IS NOT NULL`."""
    from src.core.database import (
        CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
        SourceAsset, SourceDocument, SourcePage,
    )
    occs = session.query(QuestionOccurrence).all()
    canon = session.query(CanonicalQuestion).all()
    review = session.query(QuestionReviewStatus).all()
    return {
        "documents": session.query(SourceDocument).count(),
        "pages": session.query(SourcePage).count(),
        "assets": session.query(SourceAsset).count(),
        "occurrences": len(occs),
        "occurrences_with_options": sum(1 for o in occs if o.options_json),
        "occurrences_with_answer": sum(
            1 for o in occs if (o.linked_answer or "").strip()),
        "canonical": len(canon),
        "canonical_with_options": sum(1 for q in canon if q.options_json),
        "review_rows": len(review),
        "review_approved": sum(1 for r in review if r.status == "approved"),
    }


def run_pipeline_once(base_dir: Path, source_root: Path, db_path: Path,
                      assets_dir: Path, tag: str) -> tuple[dict, dict, dict]:
    from src.core.database import get_engine, get_session_factory, init_db
    from src.pipeline.pipeline import run_pipeline

    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)
    session = get_session_factory(engine)()
    before = _counts(session)
    run = run_pipeline(session, source_root, repo_name=REPO_NAME, batch=tag,
                       version=PIPELINE_VERSION, assets_dir=str(assets_dir))
    after = _counts(session)
    stats = run.stats_json or {}
    session.close()
    return before, after, stats


def dump_occurrences(session) -> list[dict]:
    """Per-occurrence view for offline root-cause analysis."""
    from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
    docs = {d.id: d.source_path for d in session.query(SourceDocument).all()}
    pages = {p.id: p for p in session.query(SourcePage).all()}
    rows = []
    for o in session.query(QuestionOccurrence).all():
        page = pages.get(o.page_id)
        rows.append({
            "doc": docs.get(o.document_id, ""),
            "page": page.page_number if page else None,
            "question_number": o.question_number,
            "options": o.options_json,
            "linked_answer": o.linked_answer,
            "canonical_question_id": o.canonical_question_id,
            "page_text": (page.text_content if page else "") or "",
            "ocr_text": (page.ocr_text if page else "") or "",
        })
    return rows


def ocr_measurements(session) -> dict:
    from src.core.database import SourceDocument, SourcePage
    docs = {d.id: d.source_path for d in session.query(SourceDocument).all()}
    min_native = 40
    m = {
        "threshold": min_native, "pages_total": 0, "pages_native": 0,
        "pages_ocr_required": 0, "pages_ocr_attempted": 0,
        "pages_ocr_success": 0, "pages_ocr_partial": 0, "pages_ocr_empty": 0,
        "pages_ocr_required_not_run": 0, "engines": {}, "versions": {},
    }
    for p in session.query(SourcePage).all():
        native = (p.text_content or "").strip()
        ocr = (p.ocr_text or "").strip()
        m["pages_total"] += 1
        if len(native) >= min_native:
            m["pages_native"] += 1
            continue
        m["pages_ocr_required"] += 1
        if p.ocr_used:
            m["pages_ocr_attempted"] += 1
            if len(ocr) >= min_native:
                m["pages_ocr_success"] += 1
            elif ocr:
                m["pages_ocr_partial"] += 1
            else:
                m["pages_ocr_empty"] += 1
            if p.ocr_engine:
                m["engines"][p.ocr_engine] = m["engines"].get(p.ocr_engine, 0) + 1
            if p.ocr_version:
                m["versions"][p.ocr_version] = m["versions"].get(p.ocr_version, 0) + 1
        else:
            m["pages_ocr_required_not_run"] += 1
    return m


def mcq_measurements(session) -> dict:
    """MCQ option metrics including the genuine-MCQ denominator.

    Occurrences are bucketed so the option-set denominator is explicit:
      key_page / non_mcq buckets are not MCQs at all;
      genuine MCQ candidates = options extracted + answer-sheet/bubble MCQs
      (no printed option text exists) + label evidence present but the set
      was rejected as unsupported (incomplete A-F/A-J runs, dot blanks).
    """
    from src.core.database import (
        CanonicalQuestion, QuestionOccurrence, SourceDocument, SourcePage,
    )
    from src.pipeline.detect import split_candidates
    from src.pipeline.link import KEY_STEM_TOKENS, _has_key_heading, _stem_tokens

    occs = session.query(QuestionOccurrence).all()
    pages = {p.id: p for p in session.query(SourcePage).all()}
    docs = {d.id: d for d in session.query(SourceDocument).all()}
    # A whole document is "not a question" only when its filename says it is
    # a key (marking scheme / answer sheet). A question paper that also
    # contains an answers page still has question pages; only the page with
    # an explicit key heading is excluded from the MCQ denominator.
    filename_key_ids = {
        i for i, d in docs.items()
        if _stem_tokens(d.source_path) & KEY_STEM_TOKENS
    }
    canon = session.query(CanonicalQuestion).all()

    buckets = Counter()
    with_options = []
    malformed = 0
    for o in occs:
        page = pages.get(o.page_id)
        native = (page.text_content if page else "") or ""
        ocr = (page.ocr_text if page else "") or ""
        text = native if len(native.strip()) >= len(ocr.strip()) else ocr
        body = ""
        for number, candidate in split_candidates(text):
            if number == o.question_number:
                body = candidate
                break
        if _has_key_heading(native) or o.document_id in filename_key_ids:
            buckets["key_or_answer_page_not_a_question"] += 1
        elif o.options_json:
            buckets["options_extracted"] += 1
            with_options.append(o)
            letters = [opt.get("letter") for opt in o.options_json]
            if letters != [chr(ord("A") + i) for i in range(len(letters))]:
                malformed += 1
        elif _mcq_evidence(body, text):
            buckets["answer_sheet_or_rejected_label_evidence"] += 1
        else:
            buckets["non_mcq"] += 1

    extracted = buckets["options_extracted"]
    genuine = extracted + buckets["answer_sheet_or_rejected_label_evidence"]
    canon_opts = [q for q in canon if q.options_json]
    return {
        "occurrences": len(occs),
        "genuine_mcq_candidates": genuine,
        "with_options_valid": extracted,
        "malformed_option_sets": malformed,
        "unresolved_option_sets": genuine - extracted,
        "bucket_breakdown": dict(buckets),
        "with_options_ge4": sum(1 for o in with_options
                                if len(o.options_json) >= 4),
        "canonical": len(canon),
        "canonical_with_options": len(canon_opts),
        "option_count_distribution": _distribution(
            len(o.options_json) for o in with_options),
    }


# Evidence helpers for the genuine-MCQ denominator.
_MCQ_CUE = re.compile(r"(?:choose|mark the letter|answer sheet"
                      r"|from a\s*-?\s*e)", re.I)
_BUBBLE_ROW = re.compile(r"^[ \t]*A[ \t]+B[ \t]+C[ \t]+D([ \t]+E)?[ \t]*$",
                         re.M)
_INLINE_LABEL = re.compile(r"(?:^|\n)[ \t]*\(?[A-E]\)?[ \t]*[.)\-:][ \t]*\S")
_BARE_LABEL = re.compile(r"(?:^|\n)[ \t]*[A-E][ \t]*\n")


def _mcq_evidence(body: str, page_text: str) -> bool:
    """Choice-question evidence when no accepted option set exists."""
    if _MCQ_CUE.search(page_text) or _BUBBLE_ROW.search(page_text):
        return True
    if len(_INLINE_LABEL.findall(body)) >= 2:
        return True
    return len(_BARE_LABEL.findall(body)) >= 2


def _distribution(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def link_measurements(session) -> dict:
    """Answer-link accuracy measured against the documented invariant:
    a link is only valid when it comes from its own document's key table
    and that document carries explicit answer-key evidence. Any link on a
    document that is NOT an answer key is a false positive."""
    from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
    from src.pipeline.link import is_answer_sheet
    docs = {d.id: d for d in session.query(SourceDocument).all()}
    key_docs = set()
    for doc in docs.values():
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        if is_answer_sheet(doc, pages):
            key_docs.add(doc.id)

    per_doc: dict[str, int] = {}
    supported = 0
    false_positive = 0
    linked = 0
    total = 0
    nvr_links = 0
    for o in session.query(QuestionOccurrence).all():
        total += 1
        if not (o.linked_answer or "").strip():
            continue
        linked += 1
        name = docs[o.document_id].source_path if o.document_id in docs else "?"
        per_doc[name] = per_doc.get(name, 0) + 1
        if "11NVRPaper2" in name:
            nvr_links += 1
        if o.document_id in key_docs:
            supported += 1
        else:
            false_positive += 1
    return {
        "links_total": linked,
        "answer_key_documents": sorted(
            docs[i].source_path for i in key_docs),
        "answer_key_supported_links": supported,
        "unresolved_links": total - linked,
        "false_positive_links": false_positive,
        "nvr_false_links_11NVRPaper2": nvr_links,
        "links_per_document": dict(sorted(per_doc.items())),
    }


def provenance_measurements(session) -> dict:
    """Provenance for promoted canonical rows, including full chain.

    A promoted canonical must resolve canonical -> its occurrence -> page ->
    document; a broken link would mean lost source attribution.
    """
    from src.core.database import (
        CanonicalQuestion, QuestionOccurrence, SourceDocument, SourcePage,
    )
    canon_ids = {q.id for q in session.query(CanonicalQuestion).all()}
    pages = {p.id for p in session.query(SourcePage).all()}
    docs = {d.id for d in session.query(SourceDocument).all()}
    chains = 0
    linked_ids = set()
    for o in session.query(QuestionOccurrence).all():
        if not o.canonical_question_id:
            continue
        linked_ids.add(o.canonical_question_id)
        if o.page_id in pages:
            page = session.get(SourcePage, o.page_id)
            if page is not None and page.document_id in docs:
                chains += 1
    return {
        "canonical": len(canon_ids),
        "canonical_with_occurrence_link": len(canon_ids & linked_ids),
        "canonical_missing_occurrence_link": len(canon_ids - linked_ids),
        "provenance_chains_complete": chains,
        "provenance_chains_broken": len(linked_ids) - chains,
    }


def asset_measurements(session, assets_dir: Path) -> dict:
    from src.core.database import SourceAsset
    rows = session.query(SourceAsset).all()
    on_disk = 0
    total_bytes = 0
    for a in rows:
        full = assets_dir / a.storage_path
        if full.exists():
            on_disk += 1
            total_bytes += full.stat().st_size
    return {"assets": len(rows), "asset_files_on_disk": on_disk,
            "asset_files_missing": len(rows) - on_disk,
            "asset_bytes_on_disk": total_bytes}


def per_document_summary(session) -> list[str]:
    from src.core.database import (
        QuestionOccurrence, SourceAsset, SourceDocument, SourcePage,
    )
    lines = []
    for doc in sorted(session.query(SourceDocument).all(),
                      key=lambda d: d.source_path):
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        occs = session.query(QuestionOccurrence).filter_by(
            document_id=doc.id).all()
        assets = session.query(SourceAsset).filter_by(
            document_id=doc.id).count()
        native = sum(len((p.text_content or "").strip()) for p in pages)
        ocr = sum(len((p.ocr_text or "").strip()) for p in pages)
        lines.append(f"{doc.source_path:<52} {len(pages):>3}pg {assets:>4}as "
                     f"{len(occs):>3}occ native={native} ocr={ocr}")
    return lines


def sample_fingerprint(sample_dir: Path) -> dict:
    """Record every sample file and its sha256 (12-char prefix)."""
    out: dict[str, str] = {}
    for name, _category in SAMPLE_FILES:
        p = sample_dir / name
        out[name] = sha256_file(p)[:12] if p.exists() else "MISSING"
    rollup = hashlib.sha256(
        "\n".join(f"{n}:{h}" for n, h in sorted(out.items())).encode()
    ).hexdigest()
    return {"files": out, "sample_sha256": rollup}


def main(argv=None) -> int:
    import os
    ap = argparse.ArgumentParser(description="Controlled real-corpus validation")
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--source-root", default="")
    ap.add_argument("--corpus-root", default=r"D:\11+ dump")
    ap.add_argument("--tag", default="new")
    ap.add_argument("--dump-json", default="")
    args = ap.parse_args(argv)

    tesseract = configure_tesseract()
    base_dir = Path(args.base_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    source_root = (Path(args.source_root).resolve() if args.source_root
                   else base_dir / "sample_corpus")
    missing = build_sample(Path(args.corpus_root), source_root)
    os.chdir(base_dir)
    assets_dir = base_dir / "assets"

    print("### RUN IDENTITY ###")
    print("pipeline_version :", PIPELINE_VERSION)
    print("sample_dir       :", source_root)
    print("base_dir         :", base_dir)
    print("tesseract        :", tesseract or "NOT FOUND")
    fp = sample_fingerprint(source_root)
    print("sample_sha256    :", fp["sample_sha256"])
    if missing:
        print("SAMPLE FILES MISSING:", missing)
    for name, category in SAMPLE_FILES:
        print(f"  {category:<18} sha={fp['files'][name]}  {name}")

    db = base_dir / f"validate_{args.tag}.db"
    if db.exists():
        db.unlink()

    new1_before, new1_after, stats = run_pipeline_once(
        base_dir, source_root, db, assets_dir, f"{args.tag}-1")
    print("\n### STAGE-BY-STAGE COUNTS (run #1) ###")
    print("counts_before:", new1_before)
    print("counts_after :", new1_after)
    print("stats:", json.dumps(stats, indent=2))

    new2_before, new2_after, _ = run_pipeline_once(
        base_dir, source_root, db, assets_dir, f"{args.tag}-2")
    print("\n### IDEMPOTENCY (run #1 vs run #2, same db) ###")
    print("new1 after :", new1_after)
    print("new2 before:", new2_before)
    print("new2 after :", new2_after)
    growth_tables = ("documents", "pages", "assets", "occurrences", "canonical")
    no_growth = {t: (new1_after[t] == new2_before[t] == new2_after[t])
                 for t in growth_tables}
    print("no_growth   :", no_growth)
    print("idempotent :", new1_after == new2_before == new2_after)

    from src.core.database import get_engine, get_session_factory
    session = get_session_factory(get_engine(f"sqlite:///{db}"))()
    print("\n### OCR MEASUREMENTS ###")
    print(json.dumps(ocr_measurements(session), indent=2))
    print("\n### MCQ / OPTION MEASUREMENTS ###")
    print(json.dumps(mcq_measurements(session), indent=2))
    print("\n### ANSWER LINK MEASUREMENTS ###")
    print(json.dumps(link_measurements(session), indent=2))
    print("\n### PROVENANCE ###")
    print(json.dumps(provenance_measurements(session), indent=2))
    print("\n### ASSETS ###")
    print(json.dumps(asset_measurements(session, assets_dir), indent=2))
    print("\n### per_document summary ###")
    for line in per_document_summary(session):
        print("  " + line)
    if args.dump_json:
        Path(args.dump_json).write_text(
            json.dumps(dump_occurrences(session), indent=1), encoding="utf-8")
        print("\ndump:", args.dump_json)
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
