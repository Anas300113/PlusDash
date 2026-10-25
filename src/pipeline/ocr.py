"""Step: OCR for scanned/image-only pages.

Deterministic detection: a page is considered scanned when native text
extraction produced nothing usable. OCR output is stored in page.ocr_text,
separate from page.text_content (native extraction).

OCR remains extraction data, not canonical content.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from src.core.database import SourcePage, SourceAsset
from src.core.logging import get_logger

if TYPE_CHECKING:
    from src.core.database import SourceDocument

log = get_logger("pipeline.ocr")

MIN_NATIVE_TEXT_CHARS = 40

# Tesseract is frequently installed but not on PATH (e.g. the default Windows
# installer puts it under "C:\\Program Files\\Tesseract-OCR"). Point
# PLUS_TESSERACT_CMD at the executable so OCR works without PATH changes. This
# is an *environment configuration* control, distinct from an extraction failure.
TESSERACT_CMD_ENV = "PLUS_TESSERACT_CMD"


def resolve_tesseract_cmd() -> str | None:
    """Return the configured tesseract executable path, or None.

    Lets the operator make an installed-but-off-PATH Tesseract usable. When
    unset, pytesseract falls back to whatever is on PATH (or fails clearly).
    """
    cmd = os.environ.get(TESSERACT_CMD_ENV, "").strip()
    return cmd or None


def _apply_tesseract_cmd(pytesseract_mod) -> None:
    """Point pytesseract at PLUS_TESSERACT_CMD when it is configured."""
    cmd = resolve_tesseract_cmd()
    if cmd:
        pytesseract_mod.pytesseract.tesseract_cmd = cmd


def ocr_engine_status() -> dict:
    """Report Tesseract availability. Distinguishes a configuration problem
    (binary missing / wrong path) from an extraction failure."""
    cmd = resolve_tesseract_cmd()
    try:
        import pytesseract
        _apply_tesseract_cmd(pytesseract)
        version = str(pytesseract.get_tesseract_version())
        return {"available": True, "version": version, "configured_cmd": cmd}
    except Exception as exc:  # binary absent, misconfigured, or off-PATH
        return {"available": False, "version": "unavailable",
                "configured_cmd": cmd, "error": str(exc)}


def is_scanned_page(page: SourcePage) -> bool:
    """Page likely needs OCR when no reliable native text exists."""
    if page.ocr_used:
        return False
    if len(page.text_content.strip()) >= MIN_NATIVE_TEXT_CHARS:
        return False
    return True


def _tesseract_version() -> str:
    """Best-effort Tesseract version string; 'unavailable' when absent."""
    try:
        import pytesseract
        _apply_tesseract_cmd(pytesseract)
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return "unavailable"


def ocr_page(session: Session, page: SourcePage,
             image_bytes: bytes | None = None,
             engine: str = "tesseract",
             version: str = "unknown") -> str:
    """OCR a single page from image bytes. Stores result on SourcePage."""
    if image_bytes is None or len(image_bytes) == 0:
        log.warning("ocr: no image bytes for page %s.%s",
                    page.document_id[:8], page.page_number)
        return ""
    try:
        from PIL import Image
        import pytesseract
        _apply_tesseract_cmd(pytesseract)  # honour PLUS_TESSERACT_CMD (off-PATH)
        img = Image.open(io.BytesIO(image_bytes))
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        text = pytesseract.image_to_string(img).strip()
    except Exception as exc:
        log.warning("ocr: failed page %s.%s: %s",
                    page.document_id[:8], page.page_number, exc)
        text = ""
    page.ocr_text = text
    page.ocr_used = True
    page.ocr_engine = engine
    page.ocr_version = version
    session.commit()
    log.info("ocr: page %s.%s -> %d chars (%s)",
             page.document_id[:8], page.page_number, len(text), engine)
    return text


def run_ocr(session: Session, docs: list["SourceDocument"],
            source_root: str | Path = "",
            assets_dir: str | Path = "data/assets",
            engine: str = "tesseract",
            version: str = "") -> dict:
    """OCR scanned pages. Only pages without reliable native text."""
    if not version:
        version = _tesseract_version()
    root = Path(source_root) if source_root else Path.cwd()
    assets_dir = Path(assets_dir)
    ocred = 0
    skipped = 0
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        asset_by_page: dict[str, int] = {}
        for a in session.query(SourceAsset).filter_by(document_id=doc.id).all():
            asset_by_page[a.page_id] = asset_by_page.get(a.page_id, 0) + 1
        for page in pages:
            if not is_scanned_page(page):
                skipped += 1
                continue
            img = _render_page(session, doc, page, root, assets_dir)
            if img is None or len(img) == 0:
                skipped += 1
                continue
            text = ocr_page(session, page, img, engine, version)
            if text:
                ocred += 1
    session.commit()
    log.info("ocr: %d ocred, %d skipped", ocred, skipped)
    return {"ocred": ocred, "skipped": skipped}


def _render_page(session: Session, doc: "SourceDocument", page: SourcePage,
                 source_root: Path, assets_dir: Path) -> bytes | None:
    """Render page to PNG bytes for OCR."""
    pdf_path = source_root / doc.source_path
    if not pdf_path.exists():
        return None
    try:
        import fitz
        with fitz.open(str(pdf_path)) as pdf:
            if page.page_number > len(pdf):
                return None
            pix = pdf[page.page_number - 1].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            return pix.tobytes("png")
    except Exception as exc:
        log.warning("ocr render: fitz failed for %s p%s: %s",
                    doc.source_path, page.page_number, exc)
    for a in session.query(SourceAsset).filter_by(page_id=page.id).all():
        try:
            full = assets_dir / a.storage_path
            if full.exists():
                return full.read_bytes()
        except Exception:
            continue
    return None
