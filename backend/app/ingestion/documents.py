"""Extract plain text from input documents (PDF / DOCX / TXT / Markdown)."""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}
SUPPORTED_SUFFIXES = {".pdf", ".docx"} | TEXT_SUFFIXES


def iter_documents(path: str | Path) -> list[Path]:
    """Resolve an input path to a list of document files.

    A file resolves to itself; a directory resolves to all supported documents
    beneath it (recursively), sorted, skipping hidden files. This lets a single
    ``--resume``/``--essay``/``--cover-letter`` argument point at a folder of
    many versions.
    """
    path = Path(path)
    if path.is_dir():
        return sorted(
            p
            for p in path.rglob("*")
            if p.is_file()
            and p.suffix.lower() in SUPPORTED_SUFFIXES
            and not p.name.startswith(".")
        )
    return [path]  # single file (existence/type validated by extract_text)


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
