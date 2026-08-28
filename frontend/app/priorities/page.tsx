"use client";

import { useEffect, useState } from "react";
import { api, toProblem, type Problem } from "@/lib/api";
import ErrorBox from "@/app/components/ErrorBox";

export default function PrioritiesPage() {
  const [guidance, setGuidance] = useState("");
  const [saved, setSaved] = useState<string | null>(null); // last-persisted value
  const [error, setError] = useState<Problem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getPreferences()
      .then((p) => {
        setGuidance(p.resume_guidance ?? "");
        setSaved(p.resume_guidance ?? "");
      })
      .catch((e) => setError(toProblem(e)))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const p = await api.updatePreferences(guidance.trim());
      setGuidance(p.resume_guidance ?? "");
      setSaved(p.resume_guidance ?? "");
    } catch (e) {
      setError(toProblem(e));
    } finally {
      setSaving(false);
    }
  }

  const dirty = guidance.trim() !== (saved ?? "");

  return (
    <div>
      <h1>Priorities</h1>
      <p className="page-intro">
        Standing guidance for the résumé tailorer — what to prioritise, keep, or drop on{" "}
        <em>every</em> generated resume. A per-application steer still takes precedence over this.
      </p>

      {loading ? (
        <p className="busy">Loading…</p>
      ) : (
        <section className="panel steer">
          <textarea
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            placeholder={
              "e.g. Prioritise substantial paid roles and published work over side projects. " +
              "Lead with ML/quant relevance. Drop toy projects first when trimming."
            }
            disabled={saving}
            style={{ minHeight: 120 }}
          />
          <div className="actions">
            <button className="primary" disabled={saving || !dirty} onClick={save}>
              {saving ? "Saving…" : "Save"}
            </button>
            {guidance.trim() && (
              <button
                disabled={saving}
                onClick={() => {
                  setGuidance("");
                }}
              >
                Clear
              </button>
            )}
            <div className="spacer" />
            {!dirty && saved && <span className="muted">Saved.</span>}
          </div>
          {error && <ErrorBox problem={error} onDismiss={() => setError(null)} />}
        </section>
      )}
    </div>
  );
}
