"""Steps: page / text / image extraction.
Image-first: every raster image is preserved as a SourceAsset with a
content hash; text extraction records confidence and ocr_used flags.
NVR content must never rely on OCR alone."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceAsset, SourceDocument, SourcePage
from src.core.hashing import sha256_bytes
from src.core.logging import get_logger

log = get_logger("pipeline.extract")


def _ensure_pages(session: Session, doc: SourceDocument, count: int) -> list[SourcePage]:
    existing = {p.page_number: p for p in session.query(SourcePage)
                .filter_by(document_id=doc.id).all()}
    pages = []
    for n in range(1, count + 1):
        if n in existing:
            pages.append(existing[n])
            continue
        p = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                       page_number=n, text_content="")
        session.add(p)
        pages.append(p)
    session.commit()
    return pages


def run_page_extract(session: Session, docs: list[SourceDocument],
                    source_root: str | Path = "") -> dict:
    total = 0
    root = Path(source_root) if source_root else Path("data/11-dump-sample")
    for doc in docs:
        if doc.file_type != "pdf":
            continue
        pdf_path = root / doc.source_path
        if not pdf_path.exists():
            log.warning("page extract: %s not found at %s", doc.source_path, pdf_path)
            continue
        try:
            pages = extract_pdf_pages(pdf_path, session, doc)
            total += len(pages)
        except Exception as exc:
            log.warning("page extract failed for %s: %s", doc.source_path, exc)
    return {"documents": len(docs), "pages": total}


def extract_pdf_pages(pdf_path: str | Path, session: Session,
                      doc: SourceDocument) -> list[SourcePage]:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages = _ensure_pages(session, doc, len(reader.pages))
    for page, obj in zip(pages, reader.pages):
        try:
            page.text_content = obj.extract_text() or ""
            page.text_confidence = 0.85 if page.text_content.strip() else 0.0
        except Exception:
            page.text_content = ""
            page.text_confidence = 0.0
    session.commit()
    return pages


def run_text_extract(session: Session, docs: list[SourceDocument],
                     source_root: str | Path) -> dict:
    root = Path(source_root)
    pages_done = 0
    for doc in docs:
        if doc.file_type != "pdf":
            continue
        pdf_path = root / doc.source_path
        if not pdf_path.exists():
            continue
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                pages = _ensure_pages(session, doc, len(pdf.pages))
                for page, pobj in zip(pages, pdf.pages):
                    text = pobj.extract_text() or ""
                    if len(text.strip()) > len(page.text_content.strip()):
                        page.text_content = text
                        page.text_confidence = 0.9
                    pages_done += 1
        except Exception as exc:
            log.warning("text extract failed for %s: %s", doc.source_path, exc)
    session.commit()
    return {"pages": pages_done}


def run_image_extract(session: Session, docs: list[SourceDocument],
                      source_root: str | Path,
                      assets_dir: str | Path = "data/assets") -> dict:
    root = Path(source_root)
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for doc in docs:
        target = root / doc.source_path
        if not target.exists():
            continue
        if doc.file_type == "pdf":
            count += _extract_pdf_images(session, doc, target, assets_dir)
        elif doc.file_type == "image":
            count += _store_image_asset(session, doc, None, target.read_bytes(),
                                        target.suffix, assets_dir)
    session.commit()
    return {"assets": count}


def _extract_pdf_images(session: Session, doc: SourceDocument, pdf_path: Path,
                        assets_dir: Path) -> int:
    """Extract embedded images per page with PyMuPDF.

    Deterministic and idempotent: one SourceAsset row per (sha256, page).
    The same image recurring on several pages keeps one row per page so
    page-level provenance is preserved; the bytes on disk are shared.
    """
    count = 0
    try:
        import fitz
    except Exception as exc:
        log.warning("image extract: fitz unavailable for %s: %s",
                    doc.source_path, exc)
        return 0
    pages = {p.page_number: p for p in session.query(SourcePage)
             .filter_by(document_id=doc.id).all()}
    try:
        with fitz.open(str(pdf_path)) as pdf:
            for n in range(1, pdf.page_count + 1):
                page_row = pages.get(n)
                try:
                    for img in pdf[n - 1].get_images(full=True):
                        xref = img[0]
                        info = pdf.extract_image(xref)
                        data = info["image"]
                        ext = "." + info.get("ext", "png")
                        count += _store_image_asset(
                            session, doc,
                            page_row.id if page_row else None,
                            data, ext, assets_dir)
                except Exception as exc:
                    log.warning("image extract failed p%s of %s: %s",
                                n, doc.source_path, exc)
    except Exception as exc:
        log.warning("pdf image pass failed for %s: %s", doc.source_path, exc)
    session.commit()
    return count


def _store_image_asset(session: Session, doc: SourceDocument, page_id: str | None,
                       data: bytes, ext: str, assets_dir: Path) -> int:
    sha = sha256_bytes(data)
    session.flush()  # make pending rows visible to the check (autoflush=False)
    exists = session.query(SourceAsset).filter_by(sha256=sha, page_id=page_id).first()
    if exists:
        return 0  # idempotent per (sha, page)
    rel = Path(sha[:2]) / (sha + ext)
    dest = assets_dir / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    session.add(SourceAsset(id=str(uuid.uuid4()), document_id=doc.id,
                            page_id=page_id, asset_type="raster",
                            mime_type="image/png" if ext == ".png" else "image/jpeg",
                            sha256=sha, storage_path=str(rel)))
    return 1
