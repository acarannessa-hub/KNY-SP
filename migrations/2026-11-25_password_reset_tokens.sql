-- ==================================================================
-- KNYC: "Forgot password" links sent by email.
-- Run ONCE in Supabase -> SQL Editor BEFORE deploying the matching code.
-- Safe to re-run.
--
-- Only a SHA-256 hash of each link is stored, so someone who can read this
-- table still cannot use a link. Links expire after 30 minutes and work once.
-- ==================================================================

begin;

create table if not exists public.password_reset_tokens (
    id            serial primary key,
    profile_id    uuid         not null references public.profiles (id) on delete cascade,
    token_hash    char(64)     not null unique,
    created_at    timestamptz  not null default current_timestamp,
    expires_at    timestamptz  not null,
    used_at       timestamptz,
    requested_ip  varchar(64)
);
create index if not exists ix_password_reset_tokens_profile on public.password_reset_tokens (profile_id, created_at);
create index if not exists ix_password_reset_tokens_ip      on public.password_reset_tokens (requested_ip, created_at);

-- Block the public Supabase REST API (anon / publishable key).
alter table public.password_reset_tokens enable row level security;

commit;
