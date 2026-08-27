"use client";

import { useEffect, useRef, useState } from "react";
import { api, type InterviewTurn } from "@/lib/api";

type Phase = "idle" | "interviewing" | "review" | "saved";

export default function ProfilePage() {
  const [profile, setProfile] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState<InterviewTurn[]>([]);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The drafted master-doc entry, editable before it is written.
  const [section, setSection] = useState("experience");
  const [markdown, setMarkdown] = useState("");
  const [saved, setSaved] = useState<{ path: string; ingested: string } | null>(null);

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getProfile()
      .then((p) => setProfile(p.markdown))
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript, phase]);

  async function step(next: InterviewTurn[]) {
    setBusy(true);
    setError(null);
    try {
      const res = await api.interviewNext(next);
      if (res.ready) {
        const draft = await api.interviewDraft(next);
        setSection(draft.section);
        setMarkdown(draft.markdown);
        setPhase("review");
      } else if (res.question) {
        setTranscript([...next, { role: "assistant", content: res.question }]);
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setPhase("interviewing");
    setTranscript([]);
    setSaved(null);
    await step([]);
  }

  async function send() {
    const text = answer.trim();
    if (!text) return;
    setAnswer("");
    await step([...transcript, { role: "user", content: text }]);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.commitEntry(section, markdown);
      setSaved({ path: res.master_doc_path, ingested: res.ingested });
      setPhase("saved");
      const p = await api.getProfile();
      setProfile(p.markdown);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Profile</h1>
      <p className="page-intro">
        Everything your résumés and cover letters are written from. To add something new, talk it
        through below — the entry is written into your master document, so a re-ingest keeps it.
      </p>

      {/* ---- interview ---- */}
      <div className="detail-head" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Add an experience</h2>
        {phase !== "idle" && phase !== "interviewing" && (
          <button className="mini" onClick={start} disabled={busy}>
            Add another
          </button>
        )}
      </div>

      <section className="panel">
        {phase === "idle" && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              I&apos;ll ask a few questions — what the problem was, what was yours as opposed to
              the team&apos;s, how it ended up, why it mattered — then draft the entry for you to
              check before anything is saved.
            </p>
            <button className="primary" onClick={start} disabled={busy}>
              Start
            </button>
          </>
        )}

        {(phase === "interviewing" || phase === "review" || phase === "saved") &&
          transcript.length > 0 && (
            <div className="chat">
              {transcript.map((t, i) => (
                <div key={i} className={`chat-turn ${t.role}`}>
                  {t.content}
                </div>
              ))}
              {busy && phase === "interviewing" && <p className="busy">Thinking…</p>}
              <div ref={endRef} />
            </div>
          )}

        {phase === "interviewing" && (
          <div className="steer" style={{ marginTop: 12 }}>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
              }}
              placeholder="Your answer…  (⌘/Ctrl + Enter to send)"
              disabled={busy}
              style={{ minHeight: 90 }}
            />
            <div className="actions">
              <button className="primary" onClick={send} disabled={busy || !answer.trim()}>
                Send
              </button>
              <button
                onClick={() => step(transcript)}
                disabled={busy || transcript.length < 2}
                title="Skip ahead and draft the entry from what you've said so far"
              >
                That&apos;s enough — draft it
              </button>
              <div className="spacer" />
              <button onClick={() => setPhase("idle")} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {phase === "review" && (
          <div className="steer" style={{ marginTop: 12 }}>
            <h3 className="resume-section-title">Review before saving</h3>
            <p className="muted" style={{ marginTop: 0, fontSize: "0.88rem" }}>
              This is written into your master document verbatim — edit anything that isn&apos;t
              right. Keep the <code>### Heading — Org, Location. Dates</code> shape so it ingests.
            </p>
            <label className="editor-field" style={{ maxWidth: 260, marginBottom: 10 }}>
              <span>Section</span>
              <input value={section} onChange={(e) => setSection(e.target.value)} />
            </label>
            <textarea
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              style={{ minHeight: 280, fontFamily: "ui-monospace, Menlo, Consolas, monospace" }}
              disabled={busy}
            />
            <div className="actions">
              <button className="primary" onClick={save} disabled={busy || !markdown.trim()}>
                {busy ? "Saving & re-ingesting…" : "Save to master-doc"}
              </button>
              <button onClick={() => setPhase("interviewing")} disabled={busy}>
                Back to questions
              </button>
            </div>
          </div>
        )}

        {phase === "saved" && saved && (
          <div style={{ marginTop: 12 }}>
            <p>
              Saved to <code>{saved.path}</code> and re-ingested.
            </p>
            <p className="muted">{saved.ingested}</p>
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </section>

      {/* ---- current profile ---- */}
      <h2>Current profile</h2>
      <section className="panel">
        {profile === null ? (
          <p className="busy">Loading…</p>
        ) : (
          <pre className="cover-letter">{profile}</pre>
        )}
      </section>
    </div>
  );
}
