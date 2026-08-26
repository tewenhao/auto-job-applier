"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type ApplicationDetail, type RankedItem } from "@/lib/api";

export default function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState<null | "regenerate" | "approve" | "submit">(null);

  useEffect(() => {
    api
      .getApplication(id)
      .then((a) => {
        setApp(a);
        setSteer(a.steer ?? "");
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  async function run<T>(kind: typeof busy, fn: () => Promise<ApplicationDetail>) {
    setBusy(kind);
    setError(null);
    try {
      const updated = await fn();
      setApp(updated);
      setSteer(updated.steer ?? "");
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }

  if (error && !app) {
    return (
      <div>
        <Link href="/" className="back-link">
          ← All applications
        </Link>
        <div className="empty">
          <p className="error">{error}</p>
        </div>
      </div>
    );
  }

  if (!app) return <p className="busy">Loading…</p>;

  const resume = app.resume;
  const anyBusy = busy !== null;

  return (
    <div>
      <Link href="/" className="back-link">
        ← All applications
      </Link>

      <div className="detail-head">
        <div>
          <h1>{app.role_title ?? "Untitled role"}</h1>
          <p className="muted">{app.company ?? "Unknown company"}</p>
        </div>
        <span className={`pill ${app.status}`}>{app.status}</span>
      </div>

      {/* ---- steer + actions ---- */}
      <section className="panel steer">
        <h2 style={{ marginTop: 0 }}>Steer the selection</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: "0.88rem" }}>
          Free-text guidance for the tailorer — e.g. <em>“include Jane Street; rank the web-raider
          project first; drop BMTC.”</em> Regenerating re-runs the pipeline and visibly changes the
          affected scores below.
        </p>
        <textarea
          value={steer}
          onChange={(e) => setSteer(e.target.value)}
          placeholder="Leave blank to regenerate without new guidance."
          disabled={anyBusy}
        />
        <div className="actions">
          <button
            className="primary"
            disabled={anyBusy}
            onClick={() =>
              run("regenerate", () =>
                api.regenerate(app.id, { steer: steer.trim() || null }),
              )
            }
          >
            {busy === "regenerate" ? "Regenerating…" : "Regenerate"}
          </button>

          <div className="spacer" />

          <button
            disabled={anyBusy || app.status === "approved" || app.status === "submitted"}
            onClick={() => run("approve", () => api.approve(app.id, false))}
          >
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
          <button
            disabled={anyBusy || app.status === "submitted"}
            onClick={() => run("submit", () => api.approve(app.id, true))}
          >
            {busy === "submit" ? "Marking…" : "Mark submitted"}
          </button>
        </div>
        {busy === "regenerate" && (
          <p className="busy" style={{ marginTop: 10 }}>
            Running company research, tailoring, and LaTeX — this takes a moment.
          </p>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      {/* ---- ranking ---- */}
      <h2>Ranking</h2>
      {resume && resume.ranking.length > 0 ? (
        <section className="panel">
          {resume.ranking.map((item, i) => (
            <RankRow key={`${item.kind}-${item.label}-${i}`} item={item} />
          ))}
        </section>
      ) : (
        <p className="muted">No ranking recorded for this application.</p>
      )}

      {/* ---- resume artifacts ---- */}
      <h2>Resume</h2>
      <section className="panel">
        {app.resume_pdf_available ? (
          <p>
            <a href={api.resumePdfUrl(app.id)} target="_blank" rel="noreferrer">
              Open compiled PDF ↗
            </a>
          </p>
        ) : (
          <p className="muted">
            No compiled PDF (no LaTeX toolchain, or not yet generated). The tailored content is
            shown below.
          </p>
        )}
        {resume && resume.skills.length > 0 && (
          <>
            <p className="muted" style={{ marginBottom: 6 }}>
              Skills
            </p>
            <ul className="skill-list">
              {resume.skills.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* ---- cover letter ---- */}
      <h2>Cover letter</h2>
      <section className="panel">
        {app.cover_letter ? (
          <pre className="cover-letter">{app.cover_letter}</pre>
        ) : (
          <p className="muted">No cover letter generated.</p>
        )}
      </section>
    </div>
  );
}

function RankRow({ item }: { item: RankedItem }) {
  return (
    <div className={`rank-row ${item.included ? "" : "excluded"}`}>
      <div className="score">{item.score}</div>
      <div>
        <div className="rank-label">
          <span className="rank-kind">{item.kind}</span>
          {item.label}
          <span className={`rank-badge ${item.included ? "in" : "out"}`}>
            {item.included ? "included" : "dropped"}
          </span>
        </div>
        <div className="rank-rationale">{item.rationale}</div>
        <div className="score-bar">
          <span style={{ width: `${Math.max(0, Math.min(100, item.score))}%` }} />
        </div>
      </div>
    </div>
  );
}
