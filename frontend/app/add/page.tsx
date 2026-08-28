"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import ErrorBox from "@/app/components/ErrorBox";
import { useEffect, useState, useSyncExternalStore } from "react";
import {
  clearIngestRun,
  getIngestServerSnapshot,
  getIngestSnapshot,
  startTextRun,
  startUrlRun,
  subscribeIngest,
} from "@/lib/runs";

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
  // Run state lives outside the component, so switching tabs mid-run keeps it.
  const { rows, running } = useSyncExternalStore(
    subscribeIngest,
    getIngestSnapshot,
    getIngestServerSnapshot,
  );

  // A full reload would abandon an in-flight run; warn before losing sight of it.
  useEffect(() => {
    if (!running) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  const urls = mode === "urls" ? parseUrls(input) : [];
  const ingested = rows.reduce((n, r) => n + r.listings.length, 0);
  const skipped = rows.filter((r) => r.status === "done" && r.error).length;

  async function run() {
    if (mode === "text") {
      await startTextRun(input);
    } else {
      await startUrlRun(urls);
    }
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
            <>
              <button onClick={() => router.push("/")}>View listings →</button>
              <button onClick={clearIngestRun}>Clear</button>
            </>
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
                  {row.status === "abandoned" && <span className="muted">? </span>}
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

                {row.status === "abandoned" && !row.error && (
                  <div className="muted ingest-error">
                    Interrupted by a page reload — may or may not have been ingested. Check
                    Listings, or run it again (re-ingesting is safe).
                  </div>
                )}

                {row.problem && <ErrorBox problem={row.problem} />}
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
