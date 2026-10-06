-- A settled step can be unavailable or skipped, rather than successfully researched.
ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS prep_step_statuses jsonb NOT NULL DEFAULT '{}'::jsonb;
