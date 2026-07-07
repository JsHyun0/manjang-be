-- 2026-07-07: 프로덕션 트리거가 구버전이라 신규 회원의 generation(기수)이
-- public.users에 복사되지 않던 문제 수정.
-- (Supabase 마이그레이션 update_sync_auth_user_trigger_copy_generation 으로 적용됨)
--
-- 1) 트리거 함수를 schema.sql의 최신 정의로 갱신 (generation 복사 포함)
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

-- 2) 기수가 비어 있는 기존 회원을 auth metadata에서 backfill (2026-07-07 실행 완료, 145행)
update public.users u
set generation = coalesce(
  nullif(btrim(au.raw_user_meta_data ->> 'generation'), ''),
  nullif(btrim(au.raw_user_meta_data ->> 'cohort'), ''),
  nullif(btrim(au.raw_user_meta_data ->> 'batch'), ''),
  u.generation
)
from auth.users au
where au.id = u.id
  and (u.generation is null or btrim(u.generation) = '')
  and coalesce(
    nullif(btrim(au.raw_user_meta_data ->> 'generation'), ''),
    nullif(btrim(au.raw_user_meta_data ->> 'cohort'), ''),
    nullif(btrim(au.raw_user_meta_data ->> 'batch'), '')
  ) is not null;
