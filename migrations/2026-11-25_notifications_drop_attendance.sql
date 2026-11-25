-- ==================================================================
-- KNYC: email notifications (member emails, meetings/events, email log)
--       and removal of the attendance feature.
-- Run ONCE in Supabase -> SQL Editor BEFORE deploying the matching code.
-- Safe to re-run.
--
-- WARNING: step 1 permanently deletes the attendance table and all of its
-- records. Back it up first if you might ever need it.
-- ==================================================================

begin;

-- 1) Attendance feature removed: drop its table and data.
drop table if exists public.attendance;

-- 2) Every roster member can have an email for notifications.
alter table public.members add column if not exists email varchar(254);
create unique index if not exists uq_members_email_lower
    on public.members (lower(email)) where email is not null;

-- 3) Meetings and events that members are reminded about.
create table if not exists public.events (
    id           serial primary key,
    title        varchar(200) not null,
    kind         varchar(20)  not null default 'meeting'
                 check (kind in ('meeting', 'event')),
    starts_at    timestamptz  not null,
    location     varchar(255),
    description  text,
    status       varchar(20)  not null default 'scheduled'
                 check (status in ('scheduled', 'cancelled')),
    created_by   varchar(150),
    created_at   timestamptz  not null default current_timestamp,
    updated_at   timestamptz  not null default current_timestamp
);
create index if not exists ix_events_starts_at on public.events (starts_at);

-- 4) One row per email the website tried to send (who, what, result).
create table if not exists public.notification_log (
    id               serial primary key,
    created_at       timestamptz  not null default current_timestamp,
    kind             varchar(30)  not null,
    batch_id         varchar(40),
    subject          varchar(255) not null,
    body             text,
    recipient_email  varchar(254),
    membership_id    varchar(64),
    recipient_name   varchar(255),
    event_id         integer references public.events (id) on delete set null,
    status           varchar(20)  not null
                     check (status in ('sent', 'failed', 'skipped')),
    error            text,
    sent_by          varchar(150),
    dedupe_key       varchar(120)
);
create index if not exists ix_notification_log_created_at on public.notification_log (created_at);
create index if not exists ix_notification_log_kind       on public.notification_log (kind);
-- The same reminder is never sent twice to the same member.
create unique index if not exists uq_notification_log_dedupe
    on public.notification_log (dedupe_key) where dedupe_key is not null;

-- Block the public Supabase REST API (anon / publishable key).
alter table public.events enable row level security;
alter table public.notification_log enable row level security;

commit;
