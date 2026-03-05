-- ============================================
-- reset.sql
-- 개발/테스트 환경 초기화 스크립트
-- 실행 위치: Supabase SQL Editor
-- ============================================

begin;

-- --------------------------------------------
-- 1) 테이블 드롭 (FK 역순)
-- --------------------------------------------
drop table if exists public.debate_participants cascade;
drop table if exists public.reservations cascade;
drop table if exists public.debates cascade;
drop table if exists public.records cascade;
drop table if exists public.users cascade;

-- --------------------------------------------
-- 2) auth 동기화 트리거/함수 정리
-- --------------------------------------------
drop trigger if exists trg_auth_users_sync_to_public_users on auth.users;
drop function if exists public.sync_auth_user_to_public_users();

-- --------------------------------------------
-- 3) 공용 함수 정리
-- --------------------------------------------
drop function if exists public.set_updated_at();

-- --------------------------------------------
-- 4) enum 정리
-- --------------------------------------------
drop type if exists public.debate_side;
drop type if exists public.debate_type;

commit;
