"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApplicationSummary } from "@/lib/api";

export default function HomePage() {
  const [apps, setApps] = useState<ApplicationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listApplications()
      .then(setApps)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div>
      <h1>Applications</h1>
      <p className="page-intro">
        Every generated application. Open one to review its ranking, steer the selection, and
        approve.
      </p>

      {error && (
        <div className="empty">
          <p className="error">Couldn&apos;t reach the API — is `ajp serve` running?</p>
          <p className="muted">{error}</p>
        </div>
      )}

      {!error && apps === null && <p className="busy">Loading…</p>}

      {!error && apps !== null && apps.length === 0 && (
        <div className="empty">
          <p>No applications yet.</p>
          <p className="muted">
            Generate one with <code>ajp generate &lt;listing-id&gt;</code>.
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
