"""Ingestion orchestration: raw inputs -> retained source docs -> master profile."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.ingestion.documents import extract_text
from app.ingestion.extract import extract_profile
from app.ingestion.github import fetch_github_profile
from app.ingestion.mapping import apply_contact, to_experience, to_skill
from app.llm import LLMClient
from app.profile.models import SourceDocument, SourceType, WritingSample
from app.profile.repository import ProfileRepository

# Source types whose text we run through structured extraction.
_EXTRACTED_TYPES = {SourceType.RESUME, SourceType.MASTER_DOC}
# Source types we keep as raw writing samples (voice signal), not extracted.
_WRITING_TYPES = {SourceType.ESSAY, SourceType.COVER_LETTER, SourceType.PORTFOLIO}


class Ingestor:
    """Runs the ingestion steps for each kind of input against one candidate."""

    def __init__(self, repo: ProfileRepository, llm: LLMClient) -> None:
        self.repo = repo
        self.llm = llm

    def ingest_document(
        self, path: str | Path, source_type: SourceType, *, candidate_id: UUID
    ) -> dict[str, int]:
        """Parse a document, retain its raw text, and fold it into the profile."""
        path = Path(path)
        text = extract_text(path)
        doc = self.repo.add_source_document(
            SourceDocument(
                candidate_id=candidate_id,
                type=source_type,
                filename=path.name,
                raw_text=text,
                parsed_at=datetime.now(UTC),
            )
        )

        summary = {"experiences": 0, "skills": 0, "writing_samples": 0}

        if source_type in _EXTRACTED_TYPES:
            extraction = extract_profile(self.llm, text, source_type)
            if extraction.contact:
                candidate = self.repo.get_candidate(candidate_id)
                if candidate is not None:
                    self.repo.update_candidate(apply_contact(candidate, extraction.contact))
            for x in extraction.experiences:
                self.repo.upsert_experience(
                    to_experience(
                        x,
                        candidate_id=candidate_id,
                        source=source_type.value,
                        source_document_id=doc.id,
                    )
                )
                summary["experiences"] += 1
            for s in extraction.skills:
                self.repo.upsert_skill(to_skill(s, candidate_id=candidate_id))
                summary["skills"] += 1

        elif source_type in _WRITING_TYPES:
            self.repo.add_writing_sample(
                WritingSample(
                    candidate_id=candidate_id,
                    text=text,
                    source=source_type.value,
                    source_document_id=doc.id,
                    tags=[source_type.value],
                )
            )
            summary["writing_samples"] += 1

        return summary

    def ingest_github(
        self, username: str, token: str | None, *, candidate_id: UUID
    ) -> dict[str, int]:
        """Pull GitHub metadata and store it on the profile."""
        profile = fetch_github_profile(username, token, candidate_id=candidate_id)
        self.repo.set_github_profile(profile)
        return {"repos": len(profile.repos), "languages": len(profile.languages)}

    def ingest_linkedin(
        self, path: str | Path, *, candidate_id: UUID, dedup: bool = True
    ) -> dict[str, int]:
        """Parse a LinkedIn export (ZIP or directory of CSVs) into the profile.

        Deterministic (no LLM). Experiences are tagged source='linkedin' so their
        precise dates win during consolidation. ``dedup`` behaves as in
        ``ingest_document``: upsert on the natural key for incremental ingest, or
        plain-insert after a ``--fresh`` clear so distinct entries never collapse.
        """
        from app.ingestion.linkedin import (
            build_linkedin_extraction,
            raw_text_from_tables,
            read_linkedin_tables,
        )

        path = Path(path)
        tables = read_linkedin_tables(path)
        doc = self.repo.add_source_document(
            SourceDocument(
                candidate_id=candidate_id,
                type=SourceType.LINKEDIN_EXPORT,
                filename=path.name,
                raw_text=raw_text_from_tables(tables),
                parsed_at=datetime.now(UTC),
            )
        )

        contact, experiences, skills, about = build_linkedin_extraction(tables)
        if contact:
            candidate = self.repo.get_candidate(candidate_id)
            if candidate is not None:
                self.repo.update_candidate(apply_contact(candidate, contact))
        write_experience = self.repo.upsert_experience if dedup else self.repo.add_experience
        for x in experiences:
            write_experience(
                to_experience(
                    x, candidate_id=candidate_id, source="linkedin", source_document_id=doc.id
                )
            )
        for s in skills:
            self.repo.upsert_skill(to_skill(s, candidate_id=candidate_id))
        if about:
            self.repo.add_writing_sample(
                WritingSample(
                    candidate_id=candidate_id,
                    text=about,
                    source="linkedin",
                    source_document_id=doc.id,
                    tags=["linkedin_summary"],
                )
            )
        return {"experiences": len(experiences), "skills": len(skills)}
