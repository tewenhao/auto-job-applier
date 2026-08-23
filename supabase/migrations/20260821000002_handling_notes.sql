-- Add handling_notes: internal guidance that constrains downstream generation
-- but is never surfaced in output (e.g. "do not claim this shipped", audience
-- framing, "never mention peer friction"). Separated from `detail` (facts +
-- voice) so generation can read it as rules, not content.

alter table experiences
    add column handling_notes text[] not null default '{}';

alter table candidate
    add column handling_notes text[] not null default '{}';
