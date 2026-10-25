"""Generate representative fixture PDFs for the extraction spike.
Covers: maths text, maths diagram, english comprehension, english
grammar, VR, NVR, answer sheet, marking scheme, worksheet.
ZIP + PPTX fixtures are built by test scripts."""
from __future__ import annotations

from pathlib import Path


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(path: Path, lines: list[str]) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               NameObject, NumberObject)
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    text = "BT /F1 11 Tf 50 800 Td 14 TL " + " Tj T* ".join(
        f"({_esc(l)})" for l in lines) + " Tj ET"
    stream = DecodedStreamObject()
    stream.set_data(text.encode("latin-1", "replace"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject()
    font.update({NameObject("/Type"): NameObject("/Font"),
                 NameObject("/Subtype"): NameObject("/Type1"),
                 NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    page[NameObject("/MediaBox")] = ArrayObject(
        [NumberObject(0), NumberObject(0), NumberObject(595), NumberObject(842)])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f)


FIXTURES: dict[str, list[str]] = {
    "maths_text.pdf": [
        "Maths Paper 1", "1. What is 34 + 12?",
        "A) 44 B) 46 C) 48",
        "2. What is 96 divided by 8?", "A) 10 B) 12 C) 14",
    ],
    "maths_diagram.pdf": [
        "Maths Paper 2 - Geometry", "1. What is the area of a rectangle",
        "with length 12cm and width 7cm?", "A) 84 B) 74 C) 94",
        "[Diagram: rectangle 12 x 7 - see image asset]",
    ],
    "english_comprehension.pdf": [
        "English Comprehension", "Read the passage:",
        "The Arctic tern migrates 70,000km each year.",
        "1. How far does the tern travel?", "A) 7,000km B) 70,000km",
        "2. Where does it breed? A) Arctic B) Antarctic",
    ],
    "english_grammar.pdf": [
        "English Grammar", "1. Which word is a conjunction?",
        "I wanted to play, but it rained. A) outside B) but",
        "2. Choose the compound sentence.",
        "A) The cat sat. B) The sun shone, but we wore coats.",
    ],
    "vr_paper.pdf": [
        "Verbal Reasoning", "1. Hot is to cold as day is to ___",
        "A) morning B) night C) sun",
        "2. CAT is coded XZG. BAT is coded ___ A) AZG B) YZG",
    ],
    "nvr_paper.pdf": [
        "Non-Verbal Reasoning", "1. Series: circle, square, circle...",
        "What comes next? A) circle B) triangle",
        "[Shape image asset required - see page image]",
        "2. Which shape is the odd one out?",
    ],
    "answer_sheet.pdf": [
        "Answer Sheet - Maths Paper 1", "1. B", "2. B",
    ],
    "marking_scheme.pdf": [
        "Marking Scheme - Maths Paper 1", "Q1: B - award 1 mark.",
        "Method: 34 + 12 = 46.", "Q2: B - award 1 mark.",
    ],
    "worksheet.pdf": [
        "Worksheet - Fractions", "1. Simplify 12/18. A) 1/2 B) 2/3",
        "2. What is 1/4 + 2/4? A) 3/8 B) 3/4",
    ],
}


def build_all(root: str | Path = "data/fixtures/spike") -> list[Path]:
    root = Path(root)
    out = []
    for name, lines in FIXTURES.items():
        p = root / name
        _pdf(p, lines)
        out.append(p)
    return out


if __name__ == "__main__":
    for p in build_all():
        print(f"wrote {p}")
