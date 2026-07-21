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
  must_change_password boolean not null default false,
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
  allow_simultaneous boolean not null default false,
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

-- --------------------------------------------
-- 8) Reusable event tournaments
-- --------------------------------------------
create table if not exists public.tournaments (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  topic text not null default '',
  description text not null default '',
  debate_format text not null default '자유토론',
  starts_on date not null,
  ends_on date not null,
  venue text not null default '',
  status text not null default 'draft' check (status in ('draft', 'open', 'ongoing', 'completed')),
  points_per_win int not null default 1 check (points_per_win between 1 and 10),
  created_by uuid references public.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_on >= starts_on)
);

create index if not exists idx_tournaments_starts_on on public.tournaments(starts_on desc);
alter table public.tournaments enable row level security;

drop trigger if exists trg_tournaments_updated_at on public.tournaments;
create trigger trg_tournaments_updated_at
before update on public.tournaments
for each row execute function public.set_updated_at();

create table if not exists public.tournament_teams (
  id uuid primary key default gen_random_uuid(),
  tournament_id uuid not null references public.tournaments(id) on delete cascade,
  client_key text not null,
  name text not null,
  group_name text not null,
  seed int not null default 0,
  experience_score numeric(4,2) not null default 0,
  created_at timestamptz not null default now(),
  unique (tournament_id, client_key)
);

create index if not exists idx_tournament_teams_event on public.tournament_teams(tournament_id);
alter table public.tournament_teams enable row level security;

create table if not exists public.tournament_team_members (
  id bigserial primary key,
  team_id uuid not null references public.tournament_teams(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete restrict,
  experience_score int not null default 1 check (experience_score between 1 and 3),
  unique (team_id, user_id)
);

create index if not exists idx_tournament_team_members_team on public.tournament_team_members(team_id);
create index if not exists idx_tournament_team_members_user on public.tournament_team_members(user_id);
alter table public.tournament_team_members enable row level security;

create table if not exists public.tournament_matches (
  id uuid primary key default gen_random_uuid(),
  tournament_id uuid not null references public.tournaments(id) on delete cascade,
  stage text not null default 'group' check (stage in ('group', 'final')),
  group_name text,
  round_label text not null default '',
  starts_at timestamptz not null,
  venue text not null default '',
  team_a_id uuid references public.tournament_teams(id) on delete set null,
  team_b_id uuid references public.tournament_teams(id) on delete set null,
  team_a_source_group text,
  team_b_source_group text,
  team_a_score numeric(8,2),
  team_b_score numeric(8,2),
  winner_team_id uuid references public.tournament_teams(id) on delete set null,
  status text not null default 'scheduled' check (status in ('scheduled', 'completed')),
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (team_a_id is not null or team_a_source_group is not null),
  check (team_b_id is not null or team_b_source_group is not null)
);

create index if not exists idx_tournament_matches_event on public.tournament_matches(tournament_id);
create index if not exists idx_tournament_matches_starts_at on public.tournament_matches(starts_at);
alter table public.tournament_matches enable row level security;

drop trigger if exists trg_tournament_matches_updated_at on public.tournament_matches;
create trigger trg_tournament_matches_updated_at
before update on public.tournament_matches
for each row execute function public.set_updated_at();

commit;
