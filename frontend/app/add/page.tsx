"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type IngestResult } from "@/lib/api";

type Row = IngestResult & { status: "pending" | "running" | "done" };

// One line per URL; blank lines and # comments are ignored (same as --file).
function parseUrls(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const url = line.trim();
    if (!url || url.startsWith("#") || seen.has(url)) continue;
    seen.add(url);
    out.push(url);
  }
  return out;
}

export default function AddListingsPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"urls" | "text">("urls");
  const [input, setInput] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);

  const urls = mode === "urls" ? parseUrls(input) : [];
  const ingested = rows.reduce((n, r) => n + r.listings.length, 0);
  const skipped = rows.filter((r) => r.status === "done" && r.error).length;

  async function run() {
    setRunning(true);
    if (mode === "text") {
      setRows([{ url: null, listings: [], expanded: false, error: null, status: "running" }]);
      try {
        const res = await api.ingestListing({ text: input });
        setRows([{ ...res, status: "done" }]);
      } catch (e) {
        const error = String((e as Error).message ?? e);
        setRows([{ url: null, listings: [], expanded: false, error, status: "done" }]);
      }
      setRunning(false);
      return;
    }

    // Sequential: each URL fetches, parses with the LLM, and scores, so this
    // shows progress rather than blocking on one long request.
    setRows(
      urls.map((url) => ({
        url,
        listings: [],
        expanded: false,
        error: null,
        status: "pending" as const,
      })),
    );
    for (let i = 0; i < urls.length; i++) {
      setRows((prev) => prev.map((r, j) => (j === i ? { ...r, status: "running" } : r)));
      let result: Row;
      try {
        const res = await api.ingestListing({ url: urls[i] });
        result = { ...res, status: "done" };
      } catch (e) {
        result = {
          url: urls[i],
          listings: [],
          expanded: false,
          error: String((e as Error).message ?? e),
          status: "done",
        };
      }
      setRows((prev) => prev.map((r, j) => (j === i ? result : r)));
    }
    setRunning(false);
  }

  const done = rows.length > 0 && !running;

  return (
    <div>
      <h1>Add listings</h1>
      <p className="page-intro">
        Paste job URLs (one per line) from your Trackr grabber. Board and search links expand into
        every matching role. Or switch to pasting a job description for pages that won&apos;t fetch.
      </p>

      <section className="panel steer">
        <div className="actions" style={{ marginTop: 0, marginBottom: 12 }}>
          <button className={mode === "urls" ? "primary" : ""} onClick={() => setMode("urls")}>
            URLs
          </button>
          <button className={mode === "text" ? "primary" : ""} onClick={() => setMode("text")}>
            Paste JD text
          </button>
        </div>

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={running}
          style={{ minHeight: mode === "urls" ? 160 : 300 }}
          placeholder={
            mode === "urls"
              ? "https://job-boards.greenhouse.io/acme/jobs/123\nhttps://jobs.lever.co/acme?commitment=Internship\n# blank lines and # comments are ignored"
              : "Paste the full job description here."
          }
        />

        <div className="actions">
          <button
            className="primary"
            disabled={running || !input.trim()}
            onClick={run}
          >
            {running
              ? "Ingesting…"
              : mode === "urls"
                ? `Ingest ${urls.length} URL${urls.length === 1 ? "" : "s"}`
                : "Ingest"}
          </button>
          {done && (
            <button onClick={() => router.push("/")}>View listings →</button>
          )}
          <div className="spacer" />
          {rows.length > 0 && (
            <span className="muted">
              {ingested} ingested{skipped ? `, ${skipped} skipped` : ""}
            </span>
          )}
        </div>
        {running && (
          <p className="busy" style={{ marginTop: 10 }}>
            Fetching, parsing, and scoring each listing — this takes a few seconds per URL.
          </p>
        )}
      </section>

      {rows.length > 0 && (
        <>
          <h2>Results</h2>
          <section className="panel">
            {rows.map((row, i) => (
              <div key={i} className="ingest-row">
                <div className="ingest-url">
                  {row.status === "running" && <span className="muted">⏳ </span>}
                  {row.status === "pending" && <span className="muted">· </span>}
                  {row.url ?? "Pasted job description"}
                </div>

                {row.expanded && (
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    board → {row.listings.length} roles
                  </div>
                )}

                {row.listings.map((l) => (
                  <div key={l.id} className="ingest-hit">
                    {l.score !== null && <span className="score-chip small">{l.score}</span>}
                    <span>
                      {l.role_title ?? "Untitled role"}
                      <span className="muted"> @ {l.company ?? "Unknown"}</span>
                    </span>
                    <span className={`pill ${l.status}`}>{l.status}</span>
                  </div>
                ))}

                {row.error && <div className="error ingest-error">{row.error}</div>}
              </div>
            ))}
          </section>
          <p className="muted" style={{ fontSize: "0.88rem" }}>
            Skips are usually careers index pages that aren&apos;t a single posting — open a
            specific role and paste that URL, or use <Link href="/add">Paste JD text</Link>.
          </p>
        </>
      )}
    </div>
  );
}
