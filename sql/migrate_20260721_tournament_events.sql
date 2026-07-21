begin;

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
create trigger trg_tournaments_updated_at before update on public.tournaments
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
create trigger trg_tournament_matches_updated_at before update on public.tournament_matches
for each row execute function public.set_updated_at();

commit;
