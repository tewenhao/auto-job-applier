"""Data-access layer over Supabase for the master profile.

Thin, obvious wrappers around the Supabase REST API. The models in ``models.py``
are the contract; this module reads and writes them. Single-user helpers
(``get_or_create_default_candidate``) sit alongside candidate-keyed methods so
the jump to multi-user later is additive.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.db.client import get_supabase
from app.profile.models import (
    Candidate,
    Experience,
    GithubProfile,
    InterviewSession,
    InterviewStatus,
    InterviewTurn,
    MasterProfile,
    Preferences,
    Skill,
    SourceDocument,
    VoiceProfile,
    WritingSample,
)


def _rows(response: Any) -> list[dict[str, Any]]:
    """Supabase's ``.data`` is loosely typed as JSON; narrow it to row dicts."""
    return cast("list[dict[str, Any]]", response.data)


def _first(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    return data[0] if data else None


class ProfileRepository:
    """CRUD + assembly for the candidate profile."""

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase()

    # --- candidate ---
    def get_or_create_default_candidate(self) -> Candidate:
        """Return the single candidate row, creating an empty one if needed."""
        existing = _first(_rows(self.client.table("candidate").select("*").limit(1).execute()))
        if existing:
            return Candidate.from_row(existing)
        created = _rows(self.client.table("candidate").insert({}).execute())[0]
        return Candidate.from_row(created)

    def get_candidate(self, candidate_id: UUID) -> Candidate | None:
        row = _first(
            _rows(
                self.client.table("candidate")
                .select("*")
                .eq("id", str(candidate_id))
                .execute()
            )
        )
        return Candidate.from_row(row) if row else None

    def update_candidate(self, candidate: Candidate) -> Candidate:
        if candidate.id is None:
            raise ValueError("update_candidate requires candidate.id")
        row = _rows(
            self.client.table("candidate")
            .update(candidate.to_row())
            .eq("id", str(candidate.id))
            .execute()
        )[0]
        return Candidate.from_row(row)

    # --- source documents ---
    def add_source_document(self, doc: SourceDocument) -> SourceDocument:
        row = _rows(self.client.table("source_documents").insert(doc.to_row()).execute())[0]
        return SourceDocument.from_row(row)

    def list_source_documents(self, candidate_id: UUID) -> list[SourceDocument]:
        rows = _rows(
            self.client.table("source_documents")
            .select("*")
            .eq("candidate_id", str(candidate_id))
            .order("created_at")
            .execute()
        )
        return [SourceDocument.from_row(r) for r in rows]

    # --- experiences (dedup on the natural key, since the unique index is
    #     an expression index PostgREST can't target with on_conflict) ---
    def upsert_experience(self, exp: Experience) -> Experience:
        """Insert, or update the existing row that shares the natural key
        (candidate_id, kind, org, title)."""
        query = (
            self.client.table("experiences")
            .select("id")
            .eq("candidate_id", str(exp.candidate_id))
            .eq("kind", str(exp.kind))
        )
        query = query.eq("org", exp.org) if exp.org is not None else query.is_("org", "null")
        query = (
            query.eq("title", exp.title)
            if exp.title is not None
            else query.is_("title", "null")
        )
        existing = _first(_rows(query.execute()))

        if existing:
            row = _rows(
                self.client.table("experiences")
                .update(exp.to_row())
                .eq("id", existing["id"])
                .execute()
            )[0]
        else:
            row = _rows(self.client.table("experiences").insert(exp.to_row()).execute())[0]
        return Experience.from_row(row)

    def list_experiences(self, candidate_id: UUID) -> list[Experience]:
        rows = _rows(
            self.client.table("experiences")
            .select("*")
            .eq("candidate_id", str(candidate_id))
            .order("start_date", desc=True)
            .execute()
        )
        return [Experience.from_row(r) for r in rows]

    def clear_experiences(self, candidate_id: UUID) -> None:
        """Delete all experiences for a candidate (used before writing a
        consolidated set)."""
        self.client.table("experiences").delete().eq(
            "candidate_id", str(candidate_id)
        ).execute()

    # --- skills (real unique constraint -> PostgREST upsert) ---
    def upsert_skill(self, skill: Skill) -> Skill:
        row = _rows(
            self.client.table("skills")
            .upsert(skill.to_row(), on_conflict="candidate_id,name")
            .execute()
        )[0]
        return Skill.from_row(row)

    def list_skills(self, candidate_id: UUID) -> list[Skill]:
        rows = _rows(
            self.client.table("skills")
            .select("*")
            .eq("candidate_id", str(candidate_id))
            .order("name")
            .execute()
        )
        return [Skill.from_row(r) for r in rows]

    def clear_skills(self, candidate_id: UUID) -> None:
        """Delete all skills for a candidate (used before writing a normalized set)."""
        self.client.table("skills").delete().eq("candidate_id", str(candidate_id)).execute()

    # --- one-per-candidate singletons ---
    def set_github_profile(self, gh: GithubProfile) -> GithubProfile:
        row = _rows(
            self.client.table("github_profile")
            .upsert(gh.to_row(), on_conflict="candidate_id")
            .execute()
        )[0]
        return GithubProfile.from_row(row)

    def get_github_profile(self, candidate_id: UUID) -> GithubProfile | None:
        row = _first(
            _rows(
                self.client.table("github_profile")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .execute()
            )
        )
        return GithubProfile.from_row(row) if row else None

    def set_voice_profile(self, voice: VoiceProfile) -> VoiceProfile:
        row = _rows(
            self.client.table("voice_profile")
            .upsert(voice.to_row(), on_conflict="candidate_id")
            .execute()
        )[0]
        return VoiceProfile.from_row(row)

    def get_voice_profile(self, candidate_id: UUID) -> VoiceProfile | None:
        row = _first(
            _rows(
                self.client.table("voice_profile")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .execute()
            )
        )
        return VoiceProfile.from_row(row) if row else None

    def set_preferences(self, prefs: Preferences) -> Preferences:
        row = _rows(
            self.client.table("preferences")
            .upsert(prefs.to_row(), on_conflict="candidate_id")
            .execute()
        )[0]
        return Preferences.from_row(row)

    def get_preferences(self, candidate_id: UUID) -> Preferences | None:
        row = _first(
            _rows(
                self.client.table("preferences")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .execute()
            )
        )
        return Preferences.from_row(row) if row else None

    # --- writing samples ---
    def add_writing_sample(self, sample: WritingSample) -> WritingSample:
        row = _rows(self.client.table("writing_samples").insert(sample.to_row()).execute())[0]
        return WritingSample.from_row(row)

    def list_writing_samples(self, candidate_id: UUID) -> list[WritingSample]:
        rows = _rows(
            self.client.table("writing_samples")
            .select("*")
            .eq("candidate_id", str(candidate_id))
            .order("created_at")
            .execute()
        )
        return [WritingSample.from_row(r) for r in rows]

    # --- interview transcript ---
    def create_interview_session(self, candidate_id: UUID) -> InterviewSession:
        row = _rows(
            self.client.table("interview_sessions")
            .insert({"candidate_id": str(candidate_id)})
            .execute()
        )[0]
        return InterviewSession.from_row(row)

    def add_interview_turn(self, turn: InterviewTurn) -> InterviewTurn:
        row = _rows(self.client.table("interview_turns").insert(turn.to_row()).execute())[0]
        return InterviewTurn.from_row(row)

    def list_interview_turns(self, session_id: UUID) -> list[InterviewTurn]:
        rows = _rows(
            self.client.table("interview_turns")
            .select("*")
            .eq("session_id", str(session_id))
            .order("seq")
            .execute()
        )
        return [InterviewTurn.from_row(r) for r in rows]

    def complete_interview_session(self, session_id: UUID) -> None:
        self.client.table("interview_sessions").update(
            {"status": InterviewStatus.COMPLETED.value, "completed_at": "now()"}
        ).eq("id", str(session_id)).execute()

    # --- assembly ---
    def get_master_profile(self, candidate_id: UUID) -> MasterProfile:
        """Assemble the full superset for a candidate."""
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"No candidate with id {candidate_id}")
        return MasterProfile(
            candidate=candidate,
            experiences=self.list_experiences(candidate_id),
            skills=self.list_skills(candidate_id),
            github=self.get_github_profile(candidate_id),
            writing_samples=self.list_writing_samples(candidate_id),
            voice=self.get_voice_profile(candidate_id),
            preferences=self.get_preferences(candidate_id),
        )
