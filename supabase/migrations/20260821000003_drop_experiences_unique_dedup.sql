-- The unique dedup index on experiences was meant to collapse exact-key
-- re-ingests, but it makes consolidation fragile: writing a merged set can throw
-- a unique violation when two canonical rows share (kind, org, title) — e.g.
-- several personal 'other' entries with null titles. Dedup is handled in code
-- (natural-key lookup at ingest, semantic merge at consolidate), so replace the
-- UNIQUE index with a plain lookup index.

drop index if exists experiences_dedup_idx;

create index if not exists experiences_natural_idx
    on experiences (candidate_id, kind, org, title);
