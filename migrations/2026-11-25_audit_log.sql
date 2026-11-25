-- ==================================================================
-- KNYC: append-only audit log for financial changes
-- Run ONCE in Supabase -> SQL Editor BEFORE deploying the matching code.
-- Safe to re-run.
-- ==================================================================

begin;

create table if not exists public.audit_log (
    id           serial primary key,
    occurred_at  timestamptz not null default current_timestamp,
    user_id      uuid,
    user_email   varchar(150),
    action       varchar(20)  not null,
    entity       varchar(40)  not null,
    record_id    varchar(64),
    summary      text,
    before       jsonb,
    after        jsonb,
    related_id   integer
);
create index if not exists ix_audit_log_occurred_at on public.audit_log (occurred_at);
create index if not exists ix_audit_log_action      on public.audit_log (action);
create index if not exists ix_audit_log_entity      on public.audit_log (entity);

-- History cannot be rewritten: UPDATE and DELETE are refused for everyone,
-- including the app's own database user. (Only someone who first drops this
-- trigger in the Supabase dashboard could change it, which itself is visible
-- in Supabase's own logs.)
create or replace function public.audit_log_is_append_only()
returns trigger language plpgsql as $$
begin
    raise exception 'audit_log is append-only: % is not allowed', tg_op;
end;
$$;

drop trigger if exists audit_log_append_only on public.audit_log;
create trigger audit_log_append_only
    before update or delete on public.audit_log
    for each row execute function public.audit_log_is_append_only();

drop trigger if exists audit_log_no_truncate on public.audit_log;
create trigger audit_log_no_truncate
    before truncate on public.audit_log
    for each statement execute function public.audit_log_is_append_only();

-- Block the public Supabase REST API (anon / publishable key) from reading it.
alter table public.audit_log enable row level security;

commit;
