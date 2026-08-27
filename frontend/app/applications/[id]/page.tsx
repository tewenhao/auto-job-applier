"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type ApplicationDetail, type RankedItem } from "@/lib/api";
import ResumeEditor from "./ResumeEditor";

export default function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState<null | "regenerate" | "approve" | "submit">(null);
  const [editing, setEditing] = useState(false);
  const [editingCover, setEditingCover] = useState(false);
  const [coverDraft, setCoverDraft] = useState("");
  const [savingCover, setSavingCover] = useState(false);

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

  async function saveCover() {
    setSavingCover(true);
    setError(null);
    try {
      const updated = await api.saveCoverLetter(id, coverDraft);
      setApp(updated);
      setEditingCover(false);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSavingCover(false);
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
          <p className="muted">
            {app.company ?? "Unknown company"}
            {app.posting_url && (
              <>
                {" · "}
                <a href={app.posting_url} target="_blank" rel="noreferrer">
                  View posting ↗
                </a>
              </>
            )}
          </p>
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
      <div className="detail-head" style={{ marginTop: 28, marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Resume</h2>
        {resume && !editing && (
          <button className="mini" disabled={anyBusy} onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
      </div>
      <section className="panel">
        {editing && resume ? (
          <ResumeEditor
            appId={app.id}
            resume={resume}
            onSaved={(updated) => {
              setApp(updated);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <>
            {app.resume_pdf_available ? (
              <p style={{ marginTop: 0 }}>
                <a href={api.resumePdfUrl(app.id)} target="_blank" rel="noreferrer">
                  Open compiled PDF ↗
                </a>
              </p>
            ) : (
              <p className="muted" style={{ marginTop: 0 }}>
                No compiled PDF (no LaTeX toolchain, or not yet generated). The tailored content is
                shown below.
              </p>
            )}

            {resume ? (
          <div className="resume-body">
            {resume.education.length > 0 && (
              <ResumeSection title="Education">
                {resume.education.map((e, i) => (
                  <ResumeEntry
                    key={`edu-${i}`}
                    heading={e.school}
                    sub={e.degree}
                    meta={[e.location, e.dates].filter(Boolean).join(" · ")}
                    bullets={e.bullets}
                  />
                ))}
              </ResumeSection>
            )}

            {resume.experience.length > 0 && (
              <ResumeSection title="Experience">
                {resume.experience.map((e, i) => (
                  <ResumeEntry
                    key={`exp-${i}`}
                    heading={e.title}
                    sub={[e.org, e.location].filter(Boolean).join(", ")}
                    meta={e.dates}
                    bullets={e.bullets}
                  />
                ))}
              </ResumeSection>
            )}

            {resume.projects.length > 0 && (
              <ResumeSection title={resume.projects_title || "Projects"}>
                {resume.projects.map((p, i) => (
                  <ResumeEntry
                    key={`proj-${i}`}
                    heading={p.name}
                    sub={p.tools}
                    meta={p.dates}
                    bullets={p.bullets}
                  />
                ))}
              </ResumeSection>
            )}

            {resume.skills.length > 0 && (
              <ResumeSection title="Skills">
                <dl className="skill-groups">
                  {resume.skills.map((g, i) => (
                    <div key={`skill-${i}`} className="skill-group">
                      <dt>{g.label}</dt>
                      <dd>{g.items}</dd>
                    </div>
                  ))}
                </dl>
              </ResumeSection>
            )}
              </div>
            ) : (
              <p className="muted">No tailored resume content on this application yet.</p>
            )}
          </>
        )}
      </section>

      {/* ---- cover letter ---- */}
      <div className="detail-head" style={{ marginTop: 28, marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Cover letter</h2>
        {!editingCover && (
          <button
            className="mini"
            disabled={anyBusy}
            onClick={() => {
              setCoverDraft(app.cover_letter ?? "");
              setEditingCover(true);
            }}
          >
            Edit
          </button>
        )}
      </div>
      <section className="panel">
        {editingCover ? (
          <div className="steer">
            <p className="muted" style={{ marginTop: 0, fontSize: "0.88rem" }}>
              Edit the letter directly. Saving re-renders the PDF from exactly what you write (no
              model call).
            </p>
            <textarea
              value={coverDraft}
              onChange={(e) => setCoverDraft(e.target.value)}
              disabled={savingCover}
              style={{ minHeight: 320, fontFamily: "ui-monospace, Menlo, Consolas, monospace" }}
            />
            <div className="actions">
              <button className="primary" disabled={savingCover} onClick={saveCover}>
                {savingCover ? "Saving & re-rendering…" : "Save & re-render"}
              </button>
              <button disabled={savingCover} onClick={() => setEditingCover(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            {app.cover_letter_pdf_available && (
              <p style={{ marginTop: 0 }}>
                <a href={api.coverLetterPdfUrl(app.id)} target="_blank" rel="noreferrer">
                  Open compiled PDF ↗
                </a>
              </p>
            )}
            {app.cover_letter ? (
              <pre className="cover-letter">{app.cover_letter}</pre>
            ) : (
              <p className="muted">No cover letter generated.</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function ResumeSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="resume-section">
      <h3 className="resume-section-title">{title}</h3>
      {children}
    </div>
  );
}

function ResumeEntry({
  heading,
  sub,
  meta,
  bullets,
}: {
  heading: string;
  sub?: string;
  meta?: string;
  bullets: string[];
}) {
  return (
    <div className="resume-entry">
      <div className="resume-entry-head">
        <span className="resume-entry-heading">{heading}</span>
        {meta && <span className="resume-entry-meta">{meta}</span>}
      </div>
      {sub && <div className="resume-entry-sub">{sub}</div>}
      {bullets.length > 0 && (
        <ul className="resume-bullets">
          {bullets.map((b, i) => (
            <li key={i}>{renderBold(b)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Convert the tailorer's **bold** markers (same ones the LaTeX renderer turns
// into \textbf{}) into <strong> for the web view.
function renderBold(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{part}</span>
    ),
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
