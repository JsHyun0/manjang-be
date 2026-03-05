-- ============================================
-- migrate_20260305_participant_nullable.sql
-- 목적:
-- 1) debate_participants.user_id NULL 허용
-- 2) debate_participants.participant_name 추가 (직접 입력 이름 보관)
-- 3) users.generation 컬럼 추가 (후보 상세정보용)
-- ============================================

begin;

alter table public.users
  add column if not exists generation text not null default '';

alter table public.debate_participants
  add column if not exists participant_name text;

-- 기존 사용자 연결 참가자의 이름 백필
update public.debate_participants dp
set participant_name = coalesce(nullif(btrim(u.name), ''), '')
from public.users u
where dp.user_id = u.id
  and (dp.participant_name is null or btrim(dp.participant_name) = '');

-- 아직 값이 없는 행은 빈 문자열로 정리
update public.debate_participants
set participant_name = ''
where participant_name is null;

alter table public.debate_participants
  alter column participant_name set default '';

alter table public.debate_participants
  alter column participant_name set not null;

alter table public.debate_participants
  alter column user_id drop not null;

commit;
