-- Module 3 — Application Generation.
--
-- One application per chosen listing, holding the generated drafts (cover
-- letter now; tailored resume content/LaTeX next) and their review status.
-- company_briefs caches per-company research so multiple roles at the same
-- company reuse it.

create table company_briefs (
    id            uuid primary key default gen_random_uuid(),
    candidate_id  uuid not null references candidate (id) on delete cascade,
    company_group text not null,          -- normalized company key
    company       text,
    brief         text,                   -- synthesized research brief (markdown)
    hooks         jsonb not null default '[]'::jsonb,  -- candidate-specific angles
    sources       jsonb not null default '[]'::jsonb,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (candidate_id, company_group)
);

create trigger company_briefs_set_updated_at
    before update on company_briefs
    for each row execute function set_updated_at();

create table applications (
    id              uuid primary key default gen_random_uuid(),
    candidate_id    uuid not null references candidate (id) on delete cascade,
    listing_id      uuid not null references listings (id) on delete cascade,

    status          text not null default 'draft' check (status in (
                        'draft', 'approved', 'submitted')),
    cover_letter    text,
    resume_content  jsonb,                 -- tailored selection (structured)
    resume_tex      text,                  -- rendered LaTeX
    resume_pdf_path text,                  -- local path if compiled
    meta            jsonb not null default '{}'::jsonb,

    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (candidate_id, listing_id)
);

create index applications_candidate_idx on applications (candidate_id);

create trigger applications_set_updated_at
    before update on applications
    for each row execute function set_updated_at();
