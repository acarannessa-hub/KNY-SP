-- ==================================================================
-- KNYC: Export Management upgrade
--   * Excel (.xlsx) as an export format
--   * a purpose for each request, an admin note on the decision,
--     approved downloads that expire, and a download counter
-- Run ONCE in Supabase -> SQL Editor BEFORE deploying the matching code.
-- Safe to re-run. Existing requests are kept.
-- ==================================================================

begin;

alter table public.export_requests drop constraint if exists ck_export_format;
alter table public.export_requests
    add constraint ck_export_format check (export_format in ('csv', 'pdf', 'xlsx'));

alter table public.export_requests add column if not exists purpose            text;
alter table public.export_requests add column if not exists decision_note      text;
alter table public.export_requests add column if not exists expires_at         timestamptz;
alter table public.export_requests add column if not exists download_count     integer not null default 0;
alter table public.export_requests add column if not exists last_downloaded_at timestamptz;

-- Requests approved before this upgrade get 7 days from now to be downloaded.
update public.export_requests
   set expires_at = current_timestamp + interval '7 days'
 where status = 'approved' and expires_at is null;

commit;
