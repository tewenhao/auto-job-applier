-- Module 1 — Candidate Profile schema.
--
-- The master profile is a *superset* of the candidate: all inputs merge here and
-- downstream generation compresses from it. Single-user today, but every table
-- is keyed by candidate_id so multi-user is an additive change (add auth + RLS),
-- not a rewrite. Applied with `supabase db push` (or `psql -f`).

-- gen_random_uuid() lives in pgcrypto (built into Postgres 13+ on Supabase).
create extension if not exists pgcrypto;

-- Auto-maintain updated_at on tables that carry it.
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- ---------------------------------------------------------------------------
-- candidate — one row per person (single-user: exactly one).
-- ---------------------------------------------------------------------------
create table candidate (
    id            uuid primary key default gen_random_uuid(),
    full_name     text,
    email         text,
    phone         text,
    location      text,
    github_url    text,
    linkedin_url  text,
    portfolio_url text,
    links         jsonb not null default '{}'::jsonb,  -- any extra profiles/urls
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create trigger candidate_set_updated_at
    before update on candidate
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- source_documents — every raw input, retained verbatim so we can re-parse.
-- ---------------------------------------------------------------------------
create table source_documents (
    id           uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references candidate (id) on delete cascade,
    type         text not null check (type in (
                     'resume', 'linkedin_export', 'essay', 'cover_letter',
                     'master_doc', 'portfolio', 'other')),
    filename     text,
    raw_text     text,
    storage_path text,
    meta         jsonb not null default '{}'::jsonb,
    parsed_at    timestamptz,
    created_at   timestamptz not null default now()
);

create index source_documents_candidate_idx on source_documents (candidate_id);
create index source_documents_type_idx on source_documents (candidate_id, type);

-- ---------------------------------------------------------------------------
-- experiences — the core. Concise summary + rich detail + evidence links.
-- ---------------------------------------------------------------------------
create table experiences (
    id                 uuid primary key default gen_random_uuid(),
    candidate_id       uuid not null references candidate (id) on delete cascade,
    kind               text not null check (kind in (
                          'work', 'project', 'education', 'leadership',
                          'award', 'open_source', 'other')),
    org                text,
    title              text,
    location           text,
    start_date         date,
    end_date           date,
    is_current         boolean not null default false,
    summary            text,          -- concise (resume-style)
    detail             text,          -- rich elaboration (the superset)
    skills             text[] not null default '{}',
    tech               text[] not null default '{}',
    highlights         jsonb not null default '[]'::jsonb,
    evidence           jsonb not null default '[]'::jsonb,  -- [{type, ref, span}]
    source             text,          -- which input, or 'interview'
    source_document_id uuid references source_documents (id) on delete set null,
    confidence         real,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create index experiences_candidate_idx on experiences (candidate_id);
-- Natural key used by the DAL to dedup/merge inputs describing the same thing.
create unique index experiences_dedup_idx
    on experiences (candidate_id, kind, coalesce(org, ''), coalesce(title, ''));

create trigger experiences_set_updated_at
    before update on experiences
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- skills — normalized, derived from experiences, editable.
-- ---------------------------------------------------------------------------
create table skills (
    id           uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references candidate (id) on delete cascade,
    name         text not null,
    category     text,
    proficiency  text,
    years        real,
    evidence     jsonb not null default '[]'::jsonb,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (candidate_id, name)
);

create index skills_candidate_idx on skills (candidate_id);

create trigger skills_set_updated_at
    before update on skills
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- github_profile — cached API metadata (no cloning). One row per candidate.
-- ---------------------------------------------------------------------------
create table github_profile (
    id           uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references candidate (id) on delete cascade,
    username     text,
    repos        jsonb not null default '[]'::jsonb,
    languages    jsonb not null default '{}'::jsonb,
    stats        jsonb not null default '{}'::jsonb,
    pulled_at    timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (candidate_id)
);

create trigger github_profile_set_updated_at
    before update on github_profile
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- writing_samples — raw excerpts kept for few-shot voice grounding.
-- ---------------------------------------------------------------------------
create table writing_samples (
    id                 uuid primary key default gen_random_uuid(),
    candidate_id       uuid not null references candidate (id) on delete cascade,
    text               text not null,
    source             text,      -- essay | cover_letter | interview | ...
    source_document_id uuid references source_documents (id) on delete set null,
    tags               text[] not null default '{}',
    created_at         timestamptz not null default now()
);

create index writing_samples_candidate_idx on writing_samples (candidate_id);

-- ---------------------------------------------------------------------------
-- voice_profile — distilled style guide (raw samples live in writing_samples).
-- ---------------------------------------------------------------------------
create table voice_profile (
    id           uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references candidate (id) on delete cascade,
    tone         text,
    summary      text,
    guide        jsonb not null default '{}'::jsonb,  -- rhythm, vocab, quirks, do/don't
    built_from   jsonb not null default '[]'::jsonb,  -- writing_sample ids used
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (candidate_id)
);

create trigger voice_profile_set_updated_at
    before update on voice_profile
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- preferences — scoreable inputs for Module 2 listing matching.
-- ---------------------------------------------------------------------------
create table preferences (
    id               uuid primary key default gen_random_uuid(),
    candidate_id     uuid not null references candidate (id) on delete cascade,
    role_types       text[] not null default '{}',
    domains          text[] not null default '{}',   -- swe | ml | quant | product | ...
    industries       text[] not null default '{}',
    company_sizes    text[] not null default '{}',
    location_markets text[] not null default '{}',   -- uk | sg | us | cn
    avoid            text[] not null default '{}',
    weights          jsonb not null default '{}'::jsonb,
    extra            jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    unique (candidate_id)
);

create trigger preferences_set_updated_at
    before update on preferences
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- interview_sessions / interview_turns — resumable, auditable transcript.
-- ---------------------------------------------------------------------------
create table interview_sessions (
    id           uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references candidate (id) on delete cascade,
    status       text not null default 'in_progress'
                    check (status in ('in_progress', 'completed', 'abandoned')),
    started_at   timestamptz not null default now(),
    completed_at timestamptz,
    meta         jsonb not null default '{}'::jsonb
);

create index interview_sessions_candidate_idx on interview_sessions (candidate_id);

create table interview_turns (
    id           uuid primary key default gen_random_uuid(),
    session_id   uuid not null references interview_sessions (id) on delete cascade,
    candidate_id uuid not null references candidate (id) on delete cascade,
    seq          integer not null,   -- ordering within the session
    role         text not null check (role in ('assistant', 'user')),
    content      text not null,
    created_at   timestamptz not null default now(),
    unique (session_id, seq)
);

create index interview_turns_session_idx on interview_turns (session_id);
