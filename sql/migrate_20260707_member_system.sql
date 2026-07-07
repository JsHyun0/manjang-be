-- 사전 등록 회원 시스템: 최초 로그인 시 비밀번호 변경 강제 플래그
-- (Supabase migration: add_users_must_change_password 로 적용됨)
alter table public.users
  add column if not exists must_change_password boolean not null default false;
