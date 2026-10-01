-- Match API upload registration for clients that rely on the database default.
-- Existing deadlines are deliberately untouched: changing live data requires
-- a separately reviewed backfill and recovery plan.
alter table public.videos
  alter column expires_at set default now() + interval '72 hours';
