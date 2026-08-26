"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ListingSummary } from "@/lib/api";

export default function ListingsPage() {
  const router = useRouter();
  const [listings, setListings] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);

  useEffect(() => {
    api
      .listListings()
      .then(setListings)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  async function generate(listingId: string) {
    setGenerating(listingId);
    setError(null);
    try {
      const app = await api.generate(listingId);
      router.push(`/applications/${app.id}`);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setGenerating(null);
    }
  }

  return (
    <div>
      <h1>Listings</h1>
      <p className="page-intro">
        Scored job listings. Generate a tailored application for any of them, then review it under{" "}
        <Link href="/applications">Applications</Link>.
      </p>

      {error && (
        <div className="empty">
          <p className="error">
            {generating ? error : "Couldn't reach the API — is `ajp serve` running?"}
          </p>
          {!generating && <p className="muted">{error}</p>}
        </div>
      )}

      {!error && listings === null && <p className="busy">Loading…</p>}

      {!error && listings !== null && listings.length === 0 && (
        <div className="empty">
          <p>No listings yet.</p>
          <p className="muted">
            Ingest some with <code>ajp listings ingest …</code>.
          </p>
        </div>
      )}

      {listings && listings.length > 0 && (
        <div className="app-list">
          {listings.map((l) => (
            <div key={l.id} className="app-card static">
              <div className="listing-main">
                {l.score !== null && <span className="score-chip">{l.score}</span>}
                <div>
                  <div className="role">{l.role_title ?? "Untitled role"}</div>
                  <div className="company">
                    {l.company ?? "Unknown company"}
                    {l.location ? ` · ${l.location}` : ""}
                  </div>
                </div>
              </div>
              <div className="listing-action">
                {l.application_id ? (
                  <Link href={`/applications/${l.application_id}`} className="btn-link">
                    View draft →
                  </Link>
                ) : (
                  <button
                    className="primary"
                    disabled={generating !== null}
                    onClick={() => generate(l.id)}
                  >
                    {generating === l.id ? "Generating…" : "Generate"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {generating && (
        <p className="busy" style={{ marginTop: 16 }}>
          Researching the company, tailoring the resume, and writing the letter — this takes a
          moment.
        </p>
      )}
    </div>
  );
}
