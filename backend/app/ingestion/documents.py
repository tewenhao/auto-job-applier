"""Extract plain text from input documents (PDF / DOCX / TXT / Markdown)."""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


def extract_text(path: str | Path) -> str:
    """Return the plain-text content of a supported document.

    Raises ``ValueError`` for unsupported types and ``FileNotFoundError`` if the
    path doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8").strip()
    raise ValueError(
        f"Unsupported document type '{suffix}'. Supported: .pdf, .docx, "
        f"{', '.join(sorted(TEXT_SUFFIXES))}."
    )


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()
