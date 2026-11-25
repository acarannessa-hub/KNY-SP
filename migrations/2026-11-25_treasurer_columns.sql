-- ==================================================================
-- KNYC: columns from the treasurer's spreadsheets + dues tracking
-- Run ONCE in Supabase -> SQL Editor BEFORE deploying the matching code.
-- Safe to re-run: every statement uses IF NOT EXISTS.
-- ==================================================================

begin;

-- Fundraising: Activity, Income_Type, ACCOUNT NO./NAME (private)
alter table public.fundraising   add column if not exists activity     varchar(255);
alter table public.fundraising   add column if not exists income_type  varchar(50);
alter table public.fundraising   add column if not exists payer        varchar(255);

-- Sponsorships: Sponsor_Type, Purpose (stored as activity)
alter table public.sponsorships  add column if not exists sponsor_type varchar(50);
alter table public.sponsorships  add column if not exists activity     varchar(255);

-- Expenses: Activity
alter table public.expenses      add column if not exists activity     varchar(255);

-- Membership fees: the dues YEAR the quarter belongs to
alter table public.membership_fees add column if not exists year integer;
update public.membership_fees
   set year = extract(year from payment_date)::int
 where year is null;

-- Dues: what each member owes per (year, quarter) and its status
create table if not exists public.dues (
    id            serial primary key,
    membership_id varchar(64) not null
                  references public.members (membership_id)
                  on delete restrict on update cascade,
    year          integer       not null,
    quarter       varchar(2)    not null check (quarter in ('Q1','Q2','Q3','Q4')),
    amount_due    numeric(12,2) not null default 0,
    amount_paid   numeric(12,2) not null default 0,
    balance       numeric(12,2) not null default 0,
    status        varchar(20)   not null check (status in ('paid','partial','unpaid','deferred')),
    updated_at    timestamptz   default current_timestamp,
    constraint uq_dues_member_period unique (membership_id, year, quarter)
);
create index if not exists ix_dues_membership_id on public.dues (membership_id);

-- The app connects with the database role and is not affected by RLS.
-- Enabling RLS with no policies blocks the public Supabase REST API
-- (anon / publishable key) from reading members' dues.
alter table public.dues enable row level security;

commit;
