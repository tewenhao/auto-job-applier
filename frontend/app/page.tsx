"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import {
  api,
  toProblem,
  type ListingSummary,
  type Problem,
  type RescoredListing,
} from "@/lib/api";
import ErrorBox from "@/app/components/ErrorBox";
import {
  clearRescore,
  getGeneratingServerSnapshot,
  getGeneratingSnapshot,
  getRescoreServerSnapshot,
  getRescoreSnapshot,
  startGenerate,
  startRescore,
  subscribeGenerating,
  subscribeRescore,
} from "@/lib/runs";

/** How a listing moved in the last rescore: the old score struck through, the
 *  new one, and which way it went. Colour carries the direction, the arrow and
 *  the numbers carry it too — colour is never the only signal. */
function ScoreChange({ change }: { change: RescoredListing }) {
  const from = change.previous_score;
  const to = change.score;
  const direction = (to ?? 0) > (from ?? 0) ? "up" : (to ?? 0) < (from ?? 0) ? "down" : "same";
  const statusMoved = change.status !== change.previous_status;

  return (
    <span className="score-change">
      {from !== to && (
        <span className={`delta delta-${direction}`}>
          <span className="delta-was">{from ?? "--"}</span>
          {direction === "up" ? "↑" : direction === "down" ? "↓" : "→"}
        </span>
      )}
      {statusMoved && (
        <span className={`status-move status-move-${change.status}`}>now {change.status}</span>
      )}
    </span>
  );
}

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
  // Tracked outside the component, like generation: a rescore takes minutes,
  // and navigating to Priorities and back should not lose sight of it.
  const rescore = useSyncExternalStore(
    subscribeRescore,
    getRescoreSnapshot,
    getRescoreServerSnapshot,
  );

  async function runRescore() {
    if (!listings) return;
    setError(null);
    try {
      await startRescore(listings.map((l) => l.id));
    } catch (e) {
      setError(toProblem(e));
    } finally {
      setListings(await api.listListings()); // whatever was scored is saved
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
        <button onClick={runRescore} disabled={rescore.running || generating !== null}>
          {rescore.running
            ? `Re-scoring… ${rescore.done}/${rescore.total}`
            : "Re-score against my preferences"}
        </button>
        <span className="muted">
          After editing <Link href="/priorities">Priorities</Link>. Nothing is re-fetched, and
          anything you&apos;ve chosen or dismissed keeps its status.
        </span>
      </div>

      {(rescore.running || rescore.finished) && (
        <div
          className={`panel rescore-summary${
            rescore.finished ? (rescore.changed > 0 ? " did-change" : " no-change") : ""
          }`}
        >
          {rescore.running ? (
            <>
              <p>
                Scoring {rescore.done} of {rescore.total} — about{" "}
                {Math.max(1, Math.round(((rescore.total - rescore.done) * 5) / 4 / 60))} min left.
                Safe to leave this page.
              </p>
              <div
                className="progress-track"
                role="progressbar"
                aria-valuenow={rescore.done}
                aria-valuemin={0}
                aria-valuemax={rescore.total}
              >
                <div
                  className="progress-fill"
                  style={{ width: `${(rescore.done / Math.max(rescore.total, 1)) * 100}%` }}
                />
              </div>
            </>
          ) : (
            <p>
              Re-scored {rescore.done} listing{rescore.done === 1 ? "" : "s"};{" "}
              <strong>{rescore.changed}</strong> changed
              {rescore.changed > 0 ? " — marked in the list below." : "; the queue is unchanged."}{" "}
              <button className="link-button" onClick={clearRescore}>
                Dismiss
              </button>
            </p>
          )}
          {rescore.flagged.length > 0 && (
            <>
              <p className="pref-hint">
                {rescore.flagged.length} you had already decided on would now be filtered out by
                your hard filters. They have been left exactly as they are — your decision stands.
              </p>
              <ul className="flagged-list">
                {rescore.flagged.map((f) => (
                  <li key={f.id}>
                    {f.role_title ?? "Untitled role"} @ {f.company ?? "Unknown"}{" "}
                    <span className="muted">
                      ({f.status}) — {f.filter_conflict}
                    </span>
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
          {listings.map((l) => {
            const change = rescore.changes[l.id];
            return (
            <div key={l.id} className={`app-card static${change ? " changed" : ""}`}>
              <div className="listing-main">
                {l.score !== null && (
                  <span className={`score-chip${change ? " score-chip-changed" : ""}`}>
                    {l.score}
                  </span>
                )}
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
                    {change && <ScoreChange change={change} />}
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
            );
          })}
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
