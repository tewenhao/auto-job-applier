"""GitHub profile ingestion via the REST API (metadata only, no cloning)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.profile.models import GithubProfile

GITHUB_API = "https://api.github.com"
MAX_REPOS = 100


def build_github_profile(
    user: dict[str, Any],
    repos: list[dict[str, Any]],
    *,
    candidate_id: UUID,
) -> GithubProfile:
    """Assemble a GithubProfile from raw API payloads (pure — easy to test)."""
    languages: Counter[str] = Counter()
    repo_out: list[dict[str, Any]] = []
    for repo in repos:
        lang = repo.get("language")
        if lang:
            languages[lang] += 1
        repo_out.append(
            {
                "name": repo.get("name"),
                "description": repo.get("description"),
                "language": lang,
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "topics": repo.get("topics", []),
                "pushed_at": repo.get("pushed_at"),
                "html_url": repo.get("html_url"),
                "is_fork": repo.get("fork", False),
            }
        )

    stats = {
        "public_repos": user.get("public_repos"),
        "followers": user.get("followers"),
        "following": user.get("following"),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "company": user.get("company"),
        "location": user.get("location"),
        "blog": user.get("blog"),
        "created_at": user.get("created_at"),
    }

    return GithubProfile(
        candidate_id=candidate_id,
        username=user.get("login"),
        repos=repo_out,
        languages=dict(languages.most_common()),
        stats=stats,
        pulled_at=datetime.now(UTC),
    )


def fetch_github_profile(
    username: str,
    token: str | None,
    *,
    candidate_id: UUID,
    max_repos: int = MAX_REPOS,
) -> GithubProfile:
    """Fetch a user's public metadata and repositories from the GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(base_url=GITHUB_API, headers=headers, timeout=30.0) as client:
        user = client.get(f"/users/{username}").raise_for_status().json()

        repos: list[dict[str, Any]] = []
        page = 1
        while len(repos) < max_repos:
            batch = (
                client.get(
                    f"/users/{username}/repos",
                    params={"per_page": 100, "page": page, "sort": "pushed"},
                )
                .raise_for_status()
                .json()
            )
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

    return build_github_profile(user, repos[:max_repos], candidate_id=candidate_id)
