"""Contract text extraction with conservative structure cleanup."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pdfplumber
from docx import Document


def _clean_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    for raw_line in lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if re.fullmatch(r"(?:page\s+)?\d+(?:\s+of\s+\d+)?", line, re.IGNORECASE):
            continue
        if cleaned and cleaned[-1] and not re.match(r"^(?:\d+(?:\.\d+)*|clause\s+\d+|section\s+\d+)\b", line, re.IGNORECASE):
            # PDF extraction often wraps one sentence across lines. Join only
            # ordinary prose; numbered headings remain on their own line.
            cleaned[-1] = f"{cleaned[-1]} {line}"
        else:
            cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)


def _extract_pdf(file_bytes: bytes) -> str:
    page_lines: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            page_lines.extend(text.splitlines())
            page_lines.append("")
    return _clean_lines(page_lines)


def _extract_docx(file_bytes: bytes) -> str:
    document = Document(io.BytesIO(file_bytes))
    lines: list[str] = []
    for paragraph in document.paragraphs:
        lines.append(paragraph.text)
    return _clean_lines(lines)


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_bytes)
    if suffix == ".docx":
        return _extract_docx(file_bytes)
    raise ValueError("Only PDF and DOCX files are supported")
