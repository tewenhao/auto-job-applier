-- Module 2 — Job Listing Ingestion.
--
-- Listings enter either manually (a pasted link or JD text) or via a scraper.
-- Each is parsed, scored against the candidate's preferences, and surfaced for
-- the user to choose. The company_group key supports the one-role-per-company
-- rule (grouping is here; the "pick exactly one" enforcement lives in the
-- dashboard/HITL layer later).

create table listings (
    id              uuid primary key default gen_random_uuid(),
    candidate_id    uuid not null references candidate (id) on delete cascade,

    source          text not null check (source in ('manual', 'scraped')),
    source_name     text,          -- uk_tracker | greenhouse | lever | manual | ...
    url             text,
    ats             text,          -- greenhouse | lever | workday | other | unknown

    company         text,
    company_group   text,          -- normalized company, for one-role-per-company
    role_title      text,
    domain          text,          -- swe | ml | quant | product | ...
    market          text,          -- uk | sg | us | cn | other
    location        text,

    jd_text         text,          -- full raw job description
    jd_summary      text,
    requirements    text[] not null default '{}',
    posted_at       date,
    deadline        date,

    score           integer,       -- 0..100 (null = not yet scored)
    score_rationale text,
    score_breakdown jsonb not null default '{}'::jsonb,

    status          text not null default 'new' check (status in (
                        'new', 'surfaced', 'filtered', 'chosen', 'dismissed', 'applied')),

    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index listings_candidate_idx on listings (candidate_id);
create index listings_status_idx on listings (candidate_id, status);
create index listings_company_group_idx on listings (candidate_id, company_group);

-- Dedup by URL when present (manual pastes / scraped rows with a link).
create unique index listings_url_idx
    on listings (candidate_id, url) where url is not null;

create trigger listings_set_updated_at
    before update on listings
    for each row execute function set_updated_at();
