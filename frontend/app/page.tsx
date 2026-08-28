"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { api, toProblem, type ListingSummary, type Problem, type RescoreResult } from "@/lib/api";
import ErrorBox from "@/app/components/ErrorBox";
import {
  getGeneratingServerSnapshot,
  getGeneratingSnapshot,
  startGenerate,
  subscribeGenerating,
} from "@/lib/runs";

export default function ListingsPage() {
  const router = useRouter();
  const [listings, setListings] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState<Problem | null>(null);
  // Tracked outside the component, so navigating away mid-generate is safe.
  const generatingIds = useSyncExternalStore(
    subscribeGenerating,
    getGeneratingSnapshot,
    getGeneratingServerSnapshot,
  );
  const generating = generatingIds[0] ?? null;
  const [rescoring, setRescoring] = useState(false);
  const [rescored, setRescored] = useState<RescoreResult | null>(null);

  async function rescore() {
    setRescoring(true);
    setError(null);
    setRescored(null);
    try {
      const result = await api.rescoreListings();
      setRescored(result);
      setListings(await api.listListings());
    } catch (e) {
      setError(toProblem(e));
    } finally {
      setRescoring(false);
    }
  }

  useEffect(() => {
    api
      .listListings()
      .then(setListings)
      .catch((e) => setError(toProblem(e)));
  }, []);

  async function generate(listingId: string) {
    setError(null);
    try {
      const appId = await startGenerate(listingId);
      if (appId) router.push(`/applications/${appId}`);
    } catch (e) {
      setError(toProblem(e));
    }
  }

  return (
    <div>
      <h1>Listings</h1>
      <p className="page-intro">
        Scored job listings. Generate a tailored application for any of them, then review it under{" "}
        <Link href="/applications">Applications</Link>.
      </p>

      {/* Scores are computed at ingestion, so changing what you're looking for
          leaves the queue ranked by the old preferences until this is run. */}
      <div className="actions" style={{ marginBottom: 16 }}>
        <button onClick={rescore} disabled={rescoring || generating !== null}>
          {rescoring ? "Re-scoring…" : "Re-score against my preferences"}
        </button>
        <span className="muted">
          After editing <Link href="/priorities">Priorities</Link>. Nothing is re-fetched, and
          anything you&apos;ve chosen or dismissed keeps its status.
        </span>
      </div>

      {rescored && (
        <div className="panel rescore-summary">
          <p>
            Re-scored {rescored.total} listing{rescored.total === 1 ? "" : "s"};{" "}
            <strong>{rescored.changed}</strong> changed.
          </p>
          {rescored.flagged.length > 0 && (
            <>
              <p className="pref-hint">
                {rescored.flagged.length} you had already decided on would now be filtered out by
                your hard filters. They have been left exactly as they are — your decision stands.
              </p>
              <ul className="flagged-list">
                {rescored.flagged.map((f) => (
                  <li key={f.id}>
                    {f.role_title ?? "Untitled role"} @ {f.company ?? "Unknown"}{" "}
                    <span className="muted">({f.status}) — {f.filter_conflict}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {error && (
        <ErrorBox problem={error} onDismiss={() => setError(null)} />
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
                  <div className="role">
                    {l.url ? (
                      <a href={l.url} target="_blank" rel="noreferrer" className="role-link">
                        {l.role_title ?? "Untitled role"} ↗
                      </a>
                    ) : (
                      (l.role_title ?? "Untitled role")
                    )}
                  </div>
                  <div className="company">
                    {l.company ?? "Unknown company"}
                    {l.location ? ` · ${l.location}` : ""}
                  </div>
                  {l.filter_conflict && (
                    <div className="filter-conflict" title="Kept because you chose it">
                      ⚑ Your filters would now exclude this: {l.filter_conflict}
                    </div>
                  )}
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
