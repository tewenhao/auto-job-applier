"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, toProblem, type ApplicationSummary, type Problem } from "@/lib/api";
import ErrorBox from "@/app/components/ErrorBox";

export default function ApplicationsPage() {
  const [apps, setApps] = useState<ApplicationSummary[] | null>(null);
  const [error, setError] = useState<Problem | null>(null);

  useEffect(() => {
    api
      .listApplications()
      .then(setApps)
      .catch((e) => setError(toProblem(e)));
  }, []);

  return (
    <div>
      <h1>Applications</h1>
      <p className="page-intro">
        Every generated draft. Open one to review its ranking, steer the selection, and approve.
      </p>

      {error && <ErrorBox problem={error} onRetry={() => window.location.reload()} />}

      {!error && apps === null && <p className="busy">Loading…</p>}

      {!error && apps !== null && apps.length === 0 && (
        <div className="empty">
          <p>No applications yet.</p>
          <p className="muted">
            Generate one from the <Link href="/">Listings</Link> tab.
          </p>
        </div>
      )}

      {apps && apps.length > 0 && (
        <div className="app-list">
          {apps.map((a) => (
            <Link key={a.id} href={`/applications/${a.id}`} className="app-card">
              <div>
                <div className="role">{a.role_title ?? "Untitled role"}</div>
                <div className="company">{a.company ?? "Unknown company"}</div>
              </div>
              <span className={`pill ${a.status}`}>{a.status}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
