"""Ingestion: turn raw inputs (resume, master doc, essays, GitHub) into the
master profile, retaining every raw input in ``source_documents``."""

from app.ingestion.pipeline import Ingestor

__all__ = ["Ingestor"]
