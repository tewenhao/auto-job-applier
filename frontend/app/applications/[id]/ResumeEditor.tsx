"use client";

import { useState } from "react";
import { api, toProblem, type Problem, type TailoredResume } from "@/lib/api";
import ErrorBox from "@/app/components/ErrorBox";

// A generic record with string fields + optional bullets, so experience,
// projects, education, and skills all reuse one editor.
type FieldSpec = { key: string; label: string; placeholder?: string };

type Entry = Record<string, unknown> & { bullets?: string[] };

function move<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length) return arr;
  const next = arr.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function EntryListEditor({
  title,
  entries,
  fields,
  hasBullets,
  blank,
  onChange,
}: {
  title: string;
  entries: Entry[];
  fields: FieldSpec[];
  hasBullets: boolean;
  blank: () => Entry;
  onChange: (next: Entry[]) => void;
}) {
  const setEntry = (i: number, patch: Partial<Entry>) =>
    onChange(entries.map((e, j) => (j === i ? { ...e, ...patch } : e)));

  return (
    <div className="editor-section">
      <div className="editor-section-head">
        <h3 className="resume-section-title">{title}</h3>
        <button className="mini" onClick={() => onChange([...entries, blank()])}>
          + Add
        </button>
      </div>

      {entries.length === 0 && <p className="muted">None.</p>}

      {entries.map((entry, i) => (
        <div key={i} className="editor-entry">
          <div className="editor-entry-toolbar">
            <button className="mini" title="Move up" onClick={() => onChange(move(entries, i, i - 1))}>
              ↑
            </button>
            <button
              className="mini"
              title="Move down"
              onClick={() => onChange(move(entries, i, i + 1))}
            >
              ↓
            </button>
            <button
              className="mini danger"
              title="Remove"
              onClick={() => onChange(entries.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>

          <div className="editor-fields">
            {fields.map((f) => (
              <label key={f.key} className="editor-field">
                <span>{f.label}</span>
                <input
                  value={(entry[f.key] as string) ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => setEntry(i, { [f.key]: e.target.value })}
                />
              </label>
            ))}
          </div>

          {hasBullets && (
            <BulletsEditor
              bullets={entry.bullets ?? []}
              onChange={(bullets) => setEntry(i, { bullets })}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function BulletsEditor({
  bullets,
  onChange,
}: {
  bullets: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="editor-bullets">
      {bullets.map((b, i) => (
        <div key={i} className="editor-bullet">
          <textarea
            value={b}
            rows={2}
            onChange={(e) => onChange(bullets.map((x, j) => (j === i ? e.target.value : x)))}
            placeholder="Bullet — **double asterisks** bold key terms."
          />
          <div className="editor-bullet-toolbar">
            <button className="mini" title="Move up" onClick={() => onChange(move(bullets, i, i - 1))}>
              ↑
            </button>
            <button
              className="mini"
              title="Move down"
              onClick={() => onChange(move(bullets, i, i + 1))}
            >
              ↓
            </button>
            <button
              className="mini danger"
              title="Remove"
              onClick={() => onChange(bullets.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        </div>
      ))}
      <button className="mini" onClick={() => onChange([...bullets, ""])}>
        + Add bullet
      </button>
    </div>
  );
}

export default function ResumeEditor({
  appId,
  resume,
  onSaved,
  onCancel,
}: {
  appId: string;
  resume: TailoredResume;
  onSaved: (updated: import("@/lib/api").ApplicationDetail) => void;
  onCancel: () => void;
}) {
  // Deep-copy so edits don't mutate the parent's state until saved.
  const [draft, setDraft] = useState<TailoredResume>(() =>
    structuredClone(resume) as TailoredResume,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<Problem | null>(null);

  const patch = (p: Partial<TailoredResume>) => setDraft({ ...draft, ...p });

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.saveResume(appId, draft);
      onSaved(updated);
    } catch (e) {
      setError(toProblem(e));
      setSaving(false);
    }
  }

  return (
    <div className="resume-editor">
      <p className="muted" style={{ marginTop: 0 }}>
        Edit the tailored content directly. Saving re-renders the PDF from exactly what you write
        (no model call); if it overflows one page the weakest items are still trimmed.
      </p>

      <EntryListEditor
        title="Education"
        entries={draft.education as unknown as Entry[]}
        fields={[
          { key: "school", label: "School" },
          { key: "degree", label: "Degree" },
          { key: "location", label: "Location" },
          { key: "dates", label: "Dates" },
        ]}
        hasBullets
        blank={() => ({ school: "", degree: "", location: "", dates: "", bullets: [] })}
        onChange={(education) => patch({ education: education as never })}
      />

      <EntryListEditor
        title="Experience"
        entries={draft.experience as unknown as Entry[]}
        fields={[
          { key: "title", label: "Title" },
          { key: "org", label: "Organisation" },
          { key: "location", label: "Location" },
          { key: "dates", label: "Dates" },
        ]}
        hasBullets
        blank={() => ({ title: "", org: "", location: "", dates: "", bullets: [] })}
        onChange={(experience) => patch({ experience: experience as never })}
      />

      <label className="editor-field" style={{ maxWidth: 320 }}>
        <span>Projects section title</span>
        <input
          value={draft.projects_title ?? "Projects"}
          onChange={(e) => patch({ projects_title: e.target.value })}
        />
      </label>

      <EntryListEditor
        title={draft.projects_title || "Projects"}
        entries={draft.projects as unknown as Entry[]}
        fields={[
          { key: "name", label: "Name" },
          { key: "tools", label: "Tools" },
          { key: "dates", label: "Dates" },
        ]}
        hasBullets
        blank={() => ({ name: "", tools: "", dates: "", bullets: [] })}
        onChange={(projects) => patch({ projects: projects as never })}
      />

      <EntryListEditor
        title="Skills"
        entries={draft.skills as unknown as Entry[]}
        fields={[
          { key: "label", label: "Group" },
          { key: "items", label: "Items (comma-separated)" },
        ]}
        hasBullets={false}
        blank={() => ({ label: "", items: "" })}
        onChange={(skills) => patch({ skills: skills as never })}
      />

      <div className="actions">
        <button className="primary" disabled={saving} onClick={save}>
          {saving ? "Saving & re-rendering…" : "Save & re-render"}
        </button>
        <button disabled={saving} onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error && <ErrorBox problem={error} onDismiss={() => setError(null)} />}
    </div>
  );
}
