"""Step: ingest. Unpack ZIP archives into a staging area (idempotent
by content hash) and expand PPTX slide text placeholders. Returns
counts; detailed extraction happens in later steps."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceDocument
from src.core.logging import get_logger

log = get_logger("pipeline.ingest")


def _stage_dir(doc: SourceDocument, staging_root: Path) -> Path:
    d = staging_root / doc.file_sha256[:2] / doc.file_sha256
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(session: Session, docs: list[SourceDocument], batch: str,
        staging_root: str | Path = "data/staged",
        source_root: str | Path = "") -> dict:
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    unpacked = 0
    archives = 0
    for doc in docs:
        if doc.file_type != "zip":
            continue
        zip_path = Path(doc.source_path)
        if not zip_path.is_absolute():
            zip_path = Path(source_root) / doc.source_path if source_root else Path.cwd() / doc.source_path
        if not zip_path.exists():
            log.warning("ingest: zip %s not found at %s", doc.source_path, zip_path)
            continue
        try:
            data = zip_path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if sha != doc.file_sha256:
                log.warning("ingest: zip %s sha mismatch (db=%s vs file=%s)",
                            doc.source_path, doc.file_sha256, sha)
            stage_dir = _stage_dir(doc, staging_root)
            names = unpack_zip_bytes(data, stage_dir)
            # Register unpacked files as new SourceDocuments (idempotently:
            # skip any (repo_name, source_path) already registered).
            session.flush()  # make pending rows visible to the exists() check
            created = 0
            for name in names:
                unpacked_file = stage_dir / name
                rel_path = str(unpacked_file.relative_to(staging_root.parent))
                exists = (session.query(SourceDocument)
                          .filter_by(repo_name=doc.repo_name,
                                     source_path=rel_path).first())
                if exists:
                    continue
                sdoc = SourceDocument(
                    id=str(__import__("uuid").uuid4()),
                    repo_name=doc.repo_name,
                    repo_url=doc.repo_url,
                    source_path=rel_path,
                    file_sha256=hashlib.sha256(unpacked_file.read_bytes()).hexdigest(),
                    file_size=unpacked_file.stat().st_size,
                    file_type="unknown",
                    rights_status=doc.rights_status,
                    rights_note=doc.rights_note,
                    ingestion_batch=batch,
                    ingestion_version=doc.ingestion_version,
                    commit_sha=doc.commit_sha,
                )
                session.add(sdoc)
                created += 1
                unpacked += 1
                log.info("ingest: unpacked %s -> %d files (%d new docs) in %s",
                         doc.source_path, len(names), created, stage_dir)
            archives += 1
        except Exception as exc:
            log.warning("ingest: failed to unpack %s: %s", doc.source_path, exc)
    session.commit()
    log.info("ingest: %d docs, %d archives unpacked", len(docs), archives)
    return {"documents": len(docs), "archives": archives, "files_unpacked": unpacked}


def unpack_zip_bytes(data: bytes, dest: Path) -> list[str]:
    """Unpack ZIP bytes deterministically; returns sorted member names."""
    import io
    names: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            target = dest / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            names.append(info.filename)
    return names
