// Typed client for the `ajp serve` dashboard API. Types mirror
// backend/app/api/schemas.py and the TailoredResume in app/generation/resume.py.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export type RankedItem = {
  kind: string; // "experience" | "project"
  label: string;
  score: number; // 0..100
  included: boolean;
  rationale: string;
};

export type EducationEntry = {
  school: string;
  location: string;
  degree: string;
  dates: string;
  bullets: string[];
};

export type ExperienceEntry = {
  title: string;
  org: string;
  location: string;
  dates: string;
  bullets: string[];
};

export type ProjectEntry = {
  name: string;
  tools: string;
  dates: string;
  bullets: string[];
};

export type SkillGroup = {
  label: string; // e.g. "Programming"
  items: string; // comma-separated, e.g. "Python, LaTeX"
};

export type TailoredResume = {
  ranking: RankedItem[];
  education: EducationEntry[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  projects_title?: string | null;
  skills: SkillGroup[];
};

export type ListingSummary = {
  id: string;
  company: string | null;
  role_title: string | null;
  location: string | null;
  domain: string | null;
  market: string | null;
  score: number | null;
  status: string;
  url: string | null; // original job-portal posting
  application_id: string | null; // existing draft for this listing, if any
  /** Set when a listing you already decided on would now fail your hard
   *  filters. It keeps its status — this is for you to judge, not the system. */
  filter_conflict: string | null;
};

export type RescoreResult = {
  total: number;
  changed: number;
  flagged: ListingSummary[];
};

export type ApplicationSummary = {
  id: string;
  listing_id: string;
  company: string | null;
  role_title: string | null;
  status: string;
};

export type ApplicationDetail = ApplicationSummary & {
  cover_letter: string | null;
  resume: TailoredResume | null;
  resume_pdf_available: boolean;
  cover_letter_pdf_available: boolean;
  steer: string | null;
  posting_url: string | null;
  notices: Problem[]; // e.g. "this résumé is 2 pages" — same shape as an error
};

export type IngestResult = {
  url: string | null;
  listings: ListingSummary[];
  expanded: boolean; // a board URL that expanded into several roles
  error: string | null; // a per-URL skip, not a server error
};

export type InterviewTurn = { role: "assistant" | "user"; content: string };

export type InterviewStep = {
  session_id: string | null;
  transcript: InterviewTurn[];
  question: string | null;
  ready: boolean;
  missing: string | null;
  resumed: boolean;
};

export type DraftedEntry = { section: string; markdown: string };

export type CommittedEntry = { master_doc_path: string; ingested: string };

export type MasterDocEntry = { section: string; heading: string; markdown: string };

export type IngestSummary = {
  filename?: string;
  username?: string;
  source_type?: string;
  summary: Record<string, number>;
};

export type Preferences = {
  /** Standing guidance for the résumé tailorer — not about listings at all. */
  resume_guidance: string | null;

  /** Hard filters: a listing that fails these is dropped before it is scored. */
  location_markets: string[];
  avoid: string[];

  /** Ranking signals: these move the 0-100 score and exclude nothing. */
  role_types: string[];
  domains: string[];
  industries: string[];
  company_sizes: string[];
};

/** A partial update. Omitted fields are left alone; `[]` and `""` clear. */
export type PreferencesUpdate = Partial<{
  resume_guidance: string;
  location_markets: string[];
  avoid: string[];
  role_types: string[];
  domains: string[];
  industries: string[];
  company_sizes: string[];
}>;

/** A failure, in the shape the API returns: what happened, and what to try. */
export type Problem = {
  code: string;
  title: string;
  message: string;
  fixes: string[];
};

/** An API failure carrying its Problem, so the UI never has to parse a string. */
export class ApiError extends Error {
  readonly problem: Problem;
  readonly status: number;

  constructor(problem: Problem, status: number) {
    super(`${problem.title}: ${problem.message}`);
    this.name = "ApiError";
    this.problem = problem;
    this.status = status;
  }
}

/** The API is down or unreachable — by far the most common failure in local use,
 *  and the one the browser reports most uselessly ("Failed to fetch"). */
const UNREACHABLE: Problem = {
  code: "api_unreachable",
  title: "Can't reach the backend",
  message: `Nothing answered at ${API_BASE}, so this page has no data to show.`,
  fixes: [
    "Start it: `cd backend && uv run ajp serve` (it listens on :8000).",
    "If it is running, check the terminal for a crash on startup.",
    "If it runs somewhere else, set NEXT_PUBLIC_API_BASE and restart `npm run dev`.",
  ],
};

/** Whatever was thrown, as something renderable. Never returns null. */
export function toProblem(e: unknown): Problem {
  if (e instanceof ApiError) return e.problem;
  const message = e instanceof Error ? e.message : String(e);
  // A thrown TypeError from fetch means the request never left the browser.
  if (e instanceof TypeError) return UNREACHABLE;
  return {
    code: "unexpected",
    title: "Something went wrong",
    message,
    fixes: [
      "Try again — some failures are transient.",
      "Check the terminal running `ajp serve` for the full error.",
    ],
  };
}

/** Read the API's error body, whichever shape it is in. */
async function problemFrom(res: Response): Promise<Problem> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    // The API sends structured problems; older/other errors send a plain string.
    if (detail && typeof detail === "object" && "title" in detail) return detail as Problem;
    if (typeof detail === "string") {
      return {
        code: "error",
        title: "That didn't work",
        message: detail,
        fixes: ["Read the message above — it says what needs to change."],
      };
    }
  } catch {
    /* non-JSON error body */
  }
  return {
    code: "http_error",
    title: `The server returned ${res.status}`,
    message: res.statusText || "No further detail was given.",
    fixes: ["Check the terminal running `ajp serve` for the full error.", "Then try again."],
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) throw new ApiError(await problemFrom(res), res.status);
  return res.json() as Promise<T>;
}

export const api = {
  listListings: () => request<ListingSummary[]>("/api/listings"),

  generate: (listing_id: string, opts?: { steer?: string | null; max_pages?: number }) =>
    request<ApplicationDetail>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        listing_id,
        steer: opts?.steer ?? null,
        max_pages: opts?.max_pages ?? 1,
      }),
    }),

  listApplications: () => request<ApplicationSummary[]>("/api/applications"),

  getApplication: (id: string) => request<ApplicationDetail>(`/api/applications/${id}`),

  approve: (id: string, submitted: boolean) =>
    request<ApplicationDetail>(`/api/applications/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ submitted }),
    }),

  regenerate: (
    id: string,
    opts: { steer?: string | null; refresh_company?: boolean; max_pages?: number },
  ) =>
    request<ApplicationDetail>(`/api/applications/${id}/regenerate`, {
      method: "POST",
      body: JSON.stringify({
        steer: opts.steer ?? null,
        refresh_company: opts.refresh_company ?? false,
        max_pages: opts.max_pages ?? 1,
      }),
    }),

  saveResume: (id: string, resume: TailoredResume, max_pages = 1) =>
    request<ApplicationDetail>(`/api/applications/${id}/resume`, {
      method: "PUT",
      body: JSON.stringify({ resume, max_pages }),
    }),

  saveCoverLetter: (id: string, cover_letter: string) =>
    request<ApplicationDetail>(`/api/applications/${id}/cover_letter`, {
      method: "PUT",
      body: JSON.stringify({ cover_letter }),
    }),

  resumePdfUrl: (id: string) => `${API_BASE}/api/applications/${id}/resume.pdf`,

  coverLetterPdfUrl: (id: string) => `${API_BASE}/api/applications/${id}/cover_letter.pdf`,

  // Re-scores what is already stored against the current preferences. No
  // fetching, no re-parsing — slow enough to warrant a busy state, but far
  // cheaper than re-ingesting.
  rescoreListings: (listing_ids?: string[]) =>
    request<RescoreResult>("/api/listings/rescore", {
      method: "POST",
      body: JSON.stringify({ listing_ids: listing_ids ?? null }),
    }),

  ingestListing: (body: { url?: string; text?: string }) =>
    request<IngestResult>("/api/listings/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getProfile: () => request<{ markdown: string }>("/api/profile"),

  // The server owns the transcript, so an interview survives a reload.
  interviewState: () => request<InterviewStep>("/api/profile/interview"),

  interviewNext: (answer?: string, fresh = false) =>
    request<InterviewStep>("/api/profile/interview", {
      method: "POST",
      body: JSON.stringify({ answer: answer ?? null, fresh }),
    }),

  interviewDraft: () =>
    request<DraftedEntry>("/api/profile/interview/draft", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  commitEntry: (section: string, markdown: string, session_id?: string | null) =>
    request<CommittedEntry>("/api/profile/entries", {
      method: "POST",
      body: JSON.stringify({ section, markdown, session_id: session_id ?? null }),
    }),

  listEntries: () => request<MasterDocEntry[]>("/api/profile/entries"),

  // An empty `markdown` deletes the entry from the master-doc.
  editEntry: (heading: string, markdown: string) =>
    request<CommittedEntry>("/api/profile/entries", {
      method: "PUT",
      body: JSON.stringify({ heading, markdown }),
    }),

  ingestDocument: async (file: File, source_type: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_type", source_type);
    // No Content-Type header: the browser sets the multipart boundary.
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/profile/ingest`, { method: "POST", body: form });
    } catch {
      throw new ApiError(UNREACHABLE, 0);
    }
    if (!res.ok) throw new ApiError(await problemFrom(res), res.status);
    return (await res.json()) as IngestSummary;
  },

  ingestGithub: () =>
    request<IngestSummary>("/api/profile/ingest/github", { method: "POST" }),

  getPreferences: () => request<Preferences>("/api/preferences"),

  // Partial by design: the résumé guidance and the listing filters share one
  // record but are edited in different sections, so each saves only its own.
  updatePreferences: (update: PreferencesUpdate) =>
    request<Preferences>("/api/preferences", {
      method: "PUT",
      body: JSON.stringify(update),
    }),
};
