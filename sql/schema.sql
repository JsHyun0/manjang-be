-- ============================================
-- Manjang Supabase Schema (Clean)
-- 실행 위치: Supabase SQL Editor
-- 권장 순서: (선택) reset.sql 실행 -> 본 스크립트 실행
-- ============================================

begin;

-- --------------------------------------------
-- 0) Extensions
-- --------------------------------------------
create extension if not exists pgcrypto;

-- --------------------------------------------
-- 1) Enums
-- --------------------------------------------
do $$ begin
  create type public.debate_side as enum ('pro', 'con');
exception
  when duplicate_object then null;
end $$;

do $$ begin
  create type public.debate_type as enum ('자유토론', 'SSU토론');
exception
  when duplicate_object then null;
end $$;

-- --------------------------------------------
-- 2) Common updated_at trigger function
-- --------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- --------------------------------------------
-- 3) Users (auth.users 연동 프로필)
-- --------------------------------------------
create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  name text not null,
  student_id text not null unique,
  major text not null,
  generation text not null default '',
  role text not null default 'member' check (role in ('member', 'admin')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_users_email on public.users(email);
create unique index if not exists idx_users_student_id on public.users(student_id);

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
before update on public.users
for each row
execute function public.set_updated_at();

-- auth.users -> public.users 동기화
create or replace function public.sync_auth_user_to_public_users()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (
    id,
    email,
    name,
    student_id,
    major,
    generation,
    role,
    created_at,
    updated_at
  )
  values (
    new.id,
    new.email,
    coalesce(
      nullif(btrim(new.raw_user_meta_data ->> 'name'), ''),
      split_part(coalesce(new.email, ''), '@', 1),
      '사용자'
    ),
    coalesce(
      nullif(btrim(new.raw_user_meta_data ->> 'student_id'), ''),
      nullif(btrim(new.raw_user_meta_data ->> 'sid'), ''),
      concat('unknown-', new.id::text)
    ),
    coalesce(
      nullif(btrim(new.raw_user_meta_data ->> 'major'), ''),
      '미입력'
    ),
    coalesce(
      nullif(btrim(new.raw_user_meta_data ->> 'generation'), ''),
      nullif(btrim(new.raw_user_meta_data ->> 'cohort'), ''),
      nullif(btrim(new.raw_user_meta_data ->> 'batch'), ''),
      ''
    ),
    'member',
    now(),
    now()
  )
  on conflict (id) do update
  set
    email = excluded.email,
    name = excluded.name,
    student_id = excluded.student_id,
    major = excluded.major,
    generation = excluded.generation,
    updated_at = now();

  return new;
end;
$$;

drop trigger if exists trg_auth_users_sync_to_public_users on auth.users;
create trigger trg_auth_users_sync_to_public_users
after insert or update of email, raw_user_meta_data on auth.users
for each row
execute function public.sync_auth_user_to_public_users();

-- 기존 auth.users 백필
insert into public.users (
  id,
  email,
  name,
  student_id,
  major,
  generation,
  role,
  created_at,
  updated_at
)
select
  au.id,
  au.email,
  coalesce(
    nullif(btrim(au.raw_user_meta_data ->> 'name'), ''),
    split_part(coalesce(au.email, ''), '@', 1),
    '사용자'
  ) as name,
  coalesce(
    nullif(btrim(au.raw_user_meta_data ->> 'student_id'), ''),
    nullif(btrim(au.raw_user_meta_data ->> 'sid'), ''),
    concat('unknown-', au.id::text)
  ) as student_id,
  coalesce(
    nullif(btrim(au.raw_user_meta_data ->> 'major'), ''),
    '미입력'
  ) as major,
  coalesce(
    nullif(btrim(au.raw_user_meta_data ->> 'generation'), ''),
    nullif(btrim(au.raw_user_meta_data ->> 'cohort'), ''),
    nullif(btrim(au.raw_user_meta_data ->> 'batch'), ''),
    ''
  ) as generation,
  'member' as role,
  now(),
  now()
from auth.users as au
on conflict (id) do update
set
  email = excluded.email,
  name = excluded.name,
  student_id = excluded.student_id,
  major = excluded.major,
  generation = excluded.generation,
  updated_at = now();

-- --------------------------------------------
-- 4) Debates
-- --------------------------------------------
create table if not exists public.debates (
  id uuid primary key default gen_random_uuid(),
  topic_text text not null,
  debate_date date not null,
  debate_type public.debate_type not null default '자유토론',
  participant_names text[] not null default '{}',
  winner_side public.debate_side,
  notes text,
  created_by uuid references public.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_debates_date on public.debates(debate_date desc);
create index if not exists idx_debates_type on public.debates(debate_type);
create index if not exists idx_debates_created_by on public.debates(created_by);

drop trigger if exists trg_debates_updated_at on public.debates;
create trigger trg_debates_updated_at
before update on public.debates
for each row
execute function public.set_updated_at();

-- --------------------------------------------
-- 5) Debate Participants (정규화 관계)
-- --------------------------------------------
create table if not exists public.debate_participants (
  id bigserial primary key,
  debate_id uuid not null references public.debates(id) on delete cascade,
  user_id uuid references public.users(id) on delete restrict,
  participant_name text not null default '',
  side public.debate_side not null,
  unique (debate_id, user_id)
);

create index if not exists idx_debate_participants_debate on public.debate_participants(debate_id);
create index if not exists idx_debate_participants_user on public.debate_participants(user_id);

-- --------------------------------------------
-- 6) Reservations
-- --------------------------------------------
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

create index if not exists idx_reservations_starts_at on public.reservations(starts_at);
create index if not exists idx_reservations_ends_at on public.reservations(ends_at);
create index if not exists idx_reservations_debate_id on public.reservations(debate_id);
create index if not exists idx_reservations_reserved_by on public.reservations(reserved_by);

drop trigger if exists trg_reservations_updated_at on public.reservations;
create trigger trg_reservations_updated_at
before update on public.reservations
for each row
execute function public.set_updated_at();

-- --------------------------------------------
-- 7) Legacy Records
-- --------------------------------------------
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

commit;
