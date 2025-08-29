-- ============================================
-- reset.sql
-- 테스트 환경 초기화를 위한 안전한 드롭 스크립트
-- - 생성 순서와 FK 의존성을 고려해 역순으로 삭제
-- - 존재하지 않아도 에러 없이 진행 (IF EXISTS, CASCADE)
-- - public 스키마 전체 드롭은 권한 이슈로 지양
-- ============================================

begin;

-- 1) FK로 가장 많이 의존되는 테이블부터 역순 삭제
drop table if exists public.debate_participants cascade;
drop table if exists public.reservations cascade;
drop table if exists public.debates cascade;
drop table if exists public.records cascade;
drop table if exists public.users cascade;

-- 2) 커스텀 타입 삭제 (테이블 삭제 후 안전)
drop type if exists public.debate_side;

commit;

-- 참고:
-- - btree_gist 등의 extension은 프로젝트/인스턴스 레벨 권한 이슈가 있어 기본적으로 유지합니다.
-- - RLS/정책/트리거 등을 추가로 삭제해야 한다면 여기서 개별 drop 문을 추가하세요.


