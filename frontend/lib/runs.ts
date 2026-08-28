// Run state that outlives a page.
//
// Ingesting a batch and generating an application are long, server-side
// operations. Holding their progress in a component's useState meant leaving
// the page threw the progress away — the work still finished and was saved,
// but you could no longer watch it. These module-level stores survive
// client-side navigation, and the ingest run is mirrored to localStorage so a
// full reload still shows the last run.

import { api, toProblem, type IngestResult, type ListingSummary, type Problem } from "@/lib/api";

export type RowStatus = "pending" | "running" | "done" | "abandoned";
/** `error` is a skip reason from a successful call ("not a single posting");
 *  `problem` is a failure with something to do about it. They are different
 *  things and read differently in the UI. */
export type Row = IngestResult & { status: RowStatus; problem?: Problem | null };

/** Failures that will hit every remaining URL in the batch too, so there is no
 *  point grinding through 30 of them to say the same thing 30 times. */
const FATAL = new Set([
  "llm_no_credit",
  "llm_auth",
  "api_unreachable",
  "database_unreachable",
  "llm_rate_limit",
]);

export type IngestState = { rows: Row[]; running: boolean };

const STORAGE_KEY = "ajp.ingestRun";
const EMPTY: IngestState = { rows: [], running: false };

let state: IngestState = EMPTY;
let hydrated = false;
const listeners = new Set<() => void>();

function persist() {
  try {
    // A run in flight is only "live" for this document; on reload it is over.
    const snapshot: IngestState = { rows: state.rows, running: false };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    /* private mode / quota — progress is still shown in-memory */
  }
}

function set(next: IngestState) {
  state = next;
  listeners.forEach((l) => l());
  persist();
}

export function subscribeIngest(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getIngestSnapshot(): IngestState {
  if (!hydrated && typeof window !== "undefined") {
    hydrated = true;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as IngestState;
        // Anything still mid-flight when the page was reloaded can't be
        // resumed or observed, so label it rather than lie about it.
        state = {
          running: false,
          rows: saved.rows.map((r) =>
            r.status === "done" ? r : { ...r, status: "abandoned" as const },
          ),
        };
      }
    } catch {
      /* corrupt or unavailable storage — start clean */
    }
  }
  return state;
}

// useSyncExternalStore needs a stable server snapshot.
export function getIngestServerSnapshot(): IngestState {
  return EMPTY;
}

export function clearIngestRun(): void {
  set(EMPTY);
}

function replaceRow(index: number, row: Row) {
  set({ ...state, rows: state.rows.map((r, i) => (i === index ? row : r)) });
}

/** Ingest URLs one at a time so progress is visible as each finishes. */
export async function startUrlRun(urls: string[]): Promise<void> {
  if (state.running) return;
  set({
    running: true,
    rows: urls.map((url) => ({
      url,
      listings: [],
      expanded: false,
      error: null,
      status: "pending" as const,
    })),
  });

  for (let i = 0; i < urls.length; i++) {
    replaceRow(i, { ...state.rows[i], status: "running" });
    try {
      const res = await api.ingestListing({ url: urls[i] });
      replaceRow(i, { ...res, status: "done" });
    } catch (e) {
      const problem = toProblem(e);
      replaceRow(i, {
        url: urls[i],
        listings: [],
        expanded: false,
        error: null,
        problem,
        status: "done",
      });
      if (FATAL.has(problem.code)) {
        // Stop, and say so on the rest rather than leaving them looking pending.
        for (let j = i + 1; j < urls.length; j++) {
          replaceRow(j, {
            url: urls[j],
            listings: [],
            expanded: false,
            error: "Not attempted — the run stopped at the failure above.",
            status: "done",
          });
        }
        break;
      }
    }
  }
  set({ ...state, running: false });
}

export async function startTextRun(text: string): Promise<void> {
  if (state.running) return;
  set({
    running: true,
    rows: [{ url: null, listings: [], expanded: false, error: null, status: "running" }],
  });
  try {
    const res = await api.ingestListing({ text });
    set({ running: false, rows: [{ ...res, status: "done" }] });
  } catch (e) {
    set({
      running: false,
      rows: [
        {
          url: null,
          listings: [],
          expanded: false,
          error: null,
          problem: toProblem(e),
          status: "done",
        },
      ],
    });
  }
}

// --- rescoring (minutes long, so it reports progress and survives a nav) ---
export type RescoreState = {
  running: boolean;
  done: number;
  total: number;
  changed: number;
  flagged: ListingSummary[];
  finished: boolean;
};

const NO_RESCORE: RescoreState = {
  running: false,
  done: 0,
  total: 0,
  changed: 0,
  flagged: [],
  finished: false,
};

// The queue is worked through in batches: the server scores a batch in
// parallel, and each batch that lands moves the progress bar. One request for
// the whole queue would be a single silent wait of a couple of minutes.
const RESCORE_BATCH = 8;

let rescoreState: RescoreState = NO_RESCORE;
const rescoreListeners = new Set<() => void>();

function setRescore(next: RescoreState) {
  rescoreState = next;
  rescoreListeners.forEach((l) => l());
}

export function subscribeRescore(listener: () => void): () => void {
  rescoreListeners.add(listener);
  return () => rescoreListeners.delete(listener);
}

export function getRescoreSnapshot(): RescoreState {
  return rescoreState;
}

export function getRescoreServerSnapshot(): RescoreState {
  return NO_RESCORE;
}

export function clearRescore(): void {
  setRescore(NO_RESCORE);
}

/** Re-score the given listings, batch by batch. Throws so the page can report
 *  a failure through the same ErrorBox as everything else. */
export async function startRescore(ids: string[]): Promise<void> {
  if (rescoreState.running) return;
  setRescore({ ...NO_RESCORE, running: true, total: ids.length });

  let changed = 0;
  const flagged: ListingSummary[] = [];
  try {
    for (let i = 0; i < ids.length; i += RESCORE_BATCH) {
      const batch = ids.slice(i, i + RESCORE_BATCH);
      const result = await api.rescoreListings(batch);
      changed += result.changed;
      flagged.push(...result.flagged);
      setRescore({
        running: true,
        done: Math.min(i + batch.length, ids.length),
        total: ids.length,
        changed,
        flagged,
        finished: false,
      });
    }
    setRescore({ ...rescoreState, running: false, finished: true });
  } catch (e) {
    // Whatever was scored before the failure is already saved; say how far it
    // got rather than pretending the run never happened.
    setRescore({ ...rescoreState, running: false, finished: true });
    throw e;
  }
}

// --- generation in flight (so the Listings page still shows it after a nav) ---
const generating = new Set<string>();
const genListeners = new Set<() => void>();
let genSnapshot: string[] = [];

// useSyncExternalStore compares snapshots by identity, so a snapshot getter has
// to return the *same* value while nothing has changed. Building a fresh array
// on each call makes every render look like a change, which React reports as
// "The result of getServerSnapshot should be cached to avoid an infinite loop".
const NO_GENERATING: string[] = [];

function emitGen() {
  genSnapshot = [...generating];
  genListeners.forEach((l) => l());
}

export function subscribeGenerating(listener: () => void): () => void {
  genListeners.add(listener);
  return () => genListeners.delete(listener);
}

export function getGeneratingSnapshot(): string[] {
  return genSnapshot;
}

export function getGeneratingServerSnapshot(): string[] {
  return NO_GENERATING;
}

/** Generate for a listing, tracking it globally so leaving the page is safe. */
export async function startGenerate(listingId: string): Promise<string | null> {
  if (generating.has(listingId)) return null;
  generating.add(listingId);
  emitGen();
  try {
    const app = await api.generate(listingId);
    return app.id;
  } finally {
    generating.delete(listingId);
    emitGen();
  }
}
