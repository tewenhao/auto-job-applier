"use client";

import { useEffect, useRef, useState } from "react";
import { api, type InterviewTurn, type MasterDocEntry } from "@/lib/api";

const SOURCE_TYPES = [
  { value: "resume", label: "Résumé" },
  { value: "cover_letter", label: "Cover letter" },
  { value: "essay", label: "Essay" },
  { value: "master_doc", label: "Master doc" },
];

type Phase = "idle" | "interviewing" | "review" | "saved";

export default function ProfilePage() {
  const [profile, setProfile] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<InterviewTurn[]>([]);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The drafted master-doc entry, editable before it is written.
  const [section, setSection] = useState("experience");
  const [markdown, setMarkdown] = useState("");
  const [saved, setSaved] = useState<{ path: string; ingested: string } | null>(null);

  // Documents & GitHub
  const [sourceType, setSourceType] = useState("resume");
  const [ingesting, setIngesting] = useState(false);
  const [ingestNote, setIngestNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Master-doc entries
  const [entries, setEntries] = useState<MasterDocEntry[] | null>(null);
  const [editing, setEditing] = useState<MasterDocEntry | null>(null);
  const [editText, setEditText] = useState("");

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getProfile()
      .then((p) => setProfile(p.markdown))
      .catch((e) => setError(String(e.message ?? e)));
    // Pick up an interview left unfinished (here or in `ajp interview`).
    api
      .interviewState()
      .then((s) => {
        if (s.session_id && s.transcript.length) {
          setSessionId(s.session_id);
          setTranscript(s.transcript);
          setPhase("interviewing");
        }
      })
      .catch(() => {
        /* nothing to resume */
      });
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript, phase]);

  const loadEntries = () =>
    api
      .listEntries()
      .then(setEntries)
      .catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    loadEntries();
  }, []);

  async function refreshProfile() {
    const p = await api.getProfile();
    setProfile(p.markdown);
    await loadEntries();
  }

  async function upload(file: File) {
    setIngesting(true);
    setIngestNote(null);
    setError(null);
    try {
      const res = await api.ingestDocument(file, sourceType);
      const counts = Object.entries(res.summary)
        .map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`)
        .join(", ");
      setIngestNote(`Ingested ${res.filename}: ${counts}`);
      await refreshProfile();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setIngesting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function pullGithub() {
    setIngesting(true);
    setIngestNote(null);
    setError(null);
    try {
      const res = await api.ingestGithub();
      const counts = Object.entries(res.summary)
        .map(([k, v]) => `${v} ${k}`)
        .join(", ");
      setIngestNote(`Pulled @${res.username}: ${counts}`);
      await refreshProfile();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setIngesting(false);
    }
  }

  async function saveEntry(remove = false) {
    if (!editing) return;
    if (remove && !confirm(`Remove "${editing.heading}" from the master document?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.editEntry(editing.heading, remove ? "" : editText);
      setEditing(null);
      await refreshProfile();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function step(answer?: string, fresh = false) {
    setBusy(true);
    setError(null);
    try {
      const res = await api.interviewNext(answer, fresh);
      setSessionId(res.session_id);
      setTranscript(res.transcript);
      if (res.ready) {
        const draft = await api.interviewDraft();
        setSection(draft.section);
        setMarkdown(draft.markdown);
        setPhase("review");
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function draftNow() {
    setBusy(true);
    setError(null);
    try {
      const draft = await api.interviewDraft();
      setSection(draft.section);
      setMarkdown(draft.markdown);
      setPhase("review");
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
    await step(undefined, true); // start a fresh session
  }

  async function send() {
    const text = answer.trim();
    if (!text) return;
    setAnswer("");
    await step(text);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.commitEntry(section, markdown, sessionId);
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

      {/* ---- documents ---- */}
      <h2>Documents</h2>
      <section className="panel">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.9rem" }}>
          Ingest a résumé, cover letter, essay or master doc (PDF, DOCX, MD, TXT). Re-uploading
          the same document updates rather than duplicates. LinkedIn exports stay on the CLI:{" "}
          <code>ajp ingest --linkedin</code>.
        </p>
        <div className="actions" style={{ marginTop: 0 }}>
          <label className="editor-field" style={{ maxWidth: 190 }}>
            <span>Type</span>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              disabled={ingesting}
            >
              {SOURCE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.md,.txt"
            disabled={ingesting}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
            }}
          />
          <div className="spacer" />
          <button onClick={pullGithub} disabled={ingesting}>
            Pull GitHub
          </button>
        </div>
        {ingesting && <p className="busy">Parsing and folding into the profile…</p>}
        {ingestNote && <p className="muted">{ingestNote}</p>}
      </section>

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
                onClick={draftNow}
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

      {/* ---- master-doc entries ---- */}
      <h2>Master-doc entries</h2>
      <section className="panel">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.9rem" }}>
          Edits are made to the master document itself, so they survive a re-ingest. To keep
          something true but off your résumés, a handling note is better than deleting it.
        </p>

        {entries === null && <p className="busy">Loading…</p>}
        {entries?.length === 0 && <p className="muted">No entries found.</p>}

        {editing ? (
          <div className="steer">
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              Editing <strong>{editing.heading}</strong> — keep the{" "}
              <code>### Heading — Org, Location. Dates</code> shape.
            </p>
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              disabled={busy}
              style={{ minHeight: 260, fontFamily: "ui-monospace, Menlo, Consolas, monospace" }}
            />
            <div className="actions">
              <button className="primary" disabled={busy} onClick={() => saveEntry(false)}>
                {busy ? "Saving & re-ingesting…" : "Save"}
              </button>
              <button disabled={busy} onClick={() => setEditing(null)}>
                Cancel
              </button>
              <div className="spacer" />
              <button className="mini danger" disabled={busy} onClick={() => saveEntry(true)}>
                Remove entry
              </button>
            </div>
          </div>
        ) : (
          entries?.map((e) => (
            <div key={`${e.section}-${e.heading}`} className="ingest-row">
              <div className="ingest-hit" style={{ justifyContent: "space-between" }}>
                <span>
                  {e.heading}
                  <span className="muted"> · {e.section}</span>
                </span>
                <button
                  className="mini"
                  onClick={() => {
                    setEditing(e);
                    setEditText(e.markdown);
                  }}
                >
                  Edit
                </button>
              </div>
            </div>
          ))
        )}
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
