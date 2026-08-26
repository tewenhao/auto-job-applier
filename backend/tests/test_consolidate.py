"""Tests for the deterministic parts of consolidation (no LLM)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.ingestion.consolidate import (
    Cluster,
    ClusterPlan,
    MergedContent,
    _merge_dates,
    _normalize_plan,
    build_canonical,
)
from app.profile.models import Evidence, Experience, ExperienceKind

CID = uuid4()


def _exp(**kw) -> Experience:
    base = dict(candidate_id=CID, kind=ExperienceKind.WORK)
    base.update(kw)
    return Experience(**base)


def test_normalize_plan_adds_missing_and_drops_bad() -> None:
    # 4 experiences; plan covers 0,1 and references an out-of-range 9.
    plan = ClusterPlan(
        clusters=[
            Cluster(members=[0, 1, 9], primary=1, canonical_kind=ExperienceKind.WORK),
        ]
    )
    out = _normalize_plan(plan, 4)
    covered = sorted(i for c in out.clusters for i in c.members)
    assert covered == [0, 1, 2, 3]  # 2 and 3 added as singletons, 9 dropped
    first = out.clusters[0]
    assert first.members == [0, 1] and first.primary == 1


def test_normalize_plan_dedups_overlaps() -> None:
    plan = ClusterPlan(
        clusters=[
            Cluster(members=[0, 1], primary=0, canonical_kind=ExperienceKind.WORK),
            Cluster(members=[1, 2], primary=2, canonical_kind=ExperienceKind.PROJECT),
        ]
    )
    out = _normalize_plan(plan, 3)
    covered = sorted(i for c in out.clusters for i in c.members)
    assert covered == [0, 1, 2]  # index 1 only counted once


def test_merge_dates() -> None:
    members = [
        _exp(start_date=date(2025, 6, 1), end_date=date(2025, 8, 1)),
        _exp(start_date=date(2025, 1, 1), is_current=True),
    ]
    start, end, is_current = _merge_dates(members)
    assert start == date(2025, 1, 1)
    assert end == date(2025, 8, 1)
    assert is_current is True


def test_build_canonical_merges_fields() -> None:
    members = [
        _exp(
            title="First Year Trading",
            org="Jane Street",
            detail="short",
            evidence=[Evidence(type="url", ref="a")],
            source="resume",
        ),
        _exp(
            title="First-Year Trading & Technology",
            org="Jane St",
            detail="the rich master-doc version",
            evidence=[Evidence(type="url", ref="b")],
            source="master_doc",
        ),
    ]
    cluster = Cluster(
        members=[0, 1],
        primary=1,
        canonical_kind=ExperienceKind.WORK,
        canonical_org="Jane Street",
        canonical_title="First-Year Trading & Technology Programme",
    )
    merged = MergedContent(
        summary="Selected for a selective programme.",
        detail="the rich master-doc version",
        skills=["Probability"],
        highlights=["1 of 75"],
        handling_notes=["Do not state a specific acceptance rate."],
    )
    canonical = build_canonical(cluster, members, merged, candidate_id=CID)
    assert canonical.title == "First-Year Trading & Technology Programme"
    assert canonical.org == "Jane Street"
    assert canonical.handling_notes == ["Do not state a specific acceptance rate."]
    assert {e.ref for e in canonical.evidence} == {"a", "b"}  # evidence unioned
    assert canonical.source == "master_doc,resume"  # sources joined, sorted
    assert canonical.detail == "the rich master-doc version"
