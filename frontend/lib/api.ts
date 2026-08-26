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

export type ExperienceEntry = {
  title?: string | null;
  org?: string | null;
  location?: string | null;
  dates?: string | null;
  bullets: string[];
};

export type ProjectEntry = {
  name?: string | null;
  tools?: string | null;
  dates?: string | null;
  bullets: string[];
};

export type TailoredResume = {
  ranking: RankedItem[];
  education: unknown[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  projects_title?: string | null;
  skills: string[];
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
  steer: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
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

  resumePdfUrl: (id: string) => `${API_BASE}/api/applications/${id}/resume.pdf`,
};
