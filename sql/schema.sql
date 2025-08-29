-- ===============================
-- Users
-- ===============================
create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  name text,
  sid text,
  role text not null default 'member' check (role in ('member','admin')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_users_email on public.users(email);
create unique index if not exists idx_users_sid on public.users(sid) where sid is not null;

-- ===============================
-- Debate side enum
-- ===============================
do $$ begin
  create type public.debate_side as enum ('pro','con');
exception when duplicate_object then null; end $$;

-- ===============================
-- Debates (토론 정보)
-- topic_text, debate_date, winner_side
-- ===============================
create table if not exists public.debates (
  id uuid primary key default gen_random_uuid(),
  topic_text text not null,
  debate_date date not null,
  winner_side public.debate_side,
  notes text,
  created_by uuid references public.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_debates_date on public.debates(debate_date desc);

-- ===============================
-- Debate participants (토론 참가자와 side)
-- ===============================
create table if not exists public.debate_participants (
  id bigserial primary key,
  debate_id uuid not null references public.debates(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete restrict,
  side public.debate_side not null,
  unique (debate_id, user_id)
);

create index if not exists idx_debate_participants_debate on public.debate_participants(debate_id);
create index if not exists idx_debate_participants_user on public.debate_participants(user_id);

-- ===============================
-- Reservations (단일 방 전제: 시간 겹침 금지)
-- starts_at, ends_at, optional debate_id
-- ===============================
create table if not exists public.reservations (
  id uuid primary key default gen_random_uuid(),
  reserved_by uuid references public.users(id) on delete restrict,
  reserved_by_name text,
  title text,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  debate_id uuid references public.debates(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_at > starts_at)
);

-- for overlap checks in app (if Postgres extension unavailable)
create index if not exists idx_reservations_time on public.reservations(starts_at, ends_at);
create index if not exists idx_reservations_debate on public.reservations(debate_id);

-- Optional: If pgvector/btree_gist is enabled, you can add exclusion constraint
-- Note: Many hosted Supabase projects allow btree_gist; wrap in DO $$
do $$ begin
  create extension if not exists btree_gist;
exception when insufficient_privilege then null; end $$;

do $$ begin
  alter table public.reservations
    add column if not exists time_range tstzrange
    generated always as (tstzrange(starts_at, ends_at, '[)')) stored;
exception when duplicate_column then null; end $$;

-- Overlap 허용: 기존 exclusion constraint 제거 (존재할 경우만)
do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conname = 'reservations_no_overlap'
      and conrelid = 'public.reservations'::regclass
  ) then
    alter table public.reservations
      drop constraint reservations_no_overlap;
  end if;
end $$;

-- Ensure compatibility if table existed before: make reserved_by nullable and add reserved_by_name
do $$ begin
  alter table public.reservations alter column reserved_by drop not null;
exception when undefined_column then null; end $$;

do $$ begin
  alter table public.reservations add column if not exists reserved_by_name text;
exception when duplicate_column then null; end $$;

-- ===============================
-- Records (전적/요약 기록: 기존 구조 유지 가능, 필요시 마이그레이션)
-- ===============================
create table if not exists public.records (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  category text not null,
  date date not null,
  summary text not null,
  "keyPoints" text[] not null default '{}',
  conclusion text not null,
  participants int not null,
  "participantNames" text[] not null default '{}',
  inserted_at timestamptz not null default now()
);

create index if not exists idx_records_date on public.records(date desc);
create index if not exists idx_records_category on public.records(category);