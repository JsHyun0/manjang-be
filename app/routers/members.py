import csv
import io
import re
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin, require_auth
from app.config import MEMBER_EMAIL_DOMAIN, MEMBER_SHEET_URL
from app.db import get_supabase
from app.models import (
    MemberProfile,
    MemberStatsRow,
    MemberSyncRequest,
    MemberSyncResult,
    MyDebateItem,
)

router = APIRouter()

STUDENT_ID_PATTERN = re.compile(r"^\d{8}$")

_NAME_HEADERS = ("이름", "성명", "name")
_STUDENT_ID_HEADERS = ("학번", "student", "sid")
_MAJOR_HEADERS = ("학과", "전공", "major")
_GENERATION_HEADERS = ("기수", "generation", "cohort")


def _member_email(student_id: str) -> str:
    return f"{student_id}@{MEMBER_EMAIL_DOMAIN}"


def _to_csv_export_url(sheet_url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    if not match:
        raise HTTPException(status_code=400, detail="구글 스프레드시트 URL 형식이 아닙니다.")
    doc_id = match.group(1)
    gid_match = re.search(r"[#?&]gid=(\d+)", sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"


def _fetch_sheet_csv(sheet_url: str) -> str:
    export_url = _to_csv_export_url(sheet_url)
    try:
        resp = httpx.get(export_url, follow_redirects=True, timeout=20.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"구글시트 요청에 실패했습니다: {exc}")

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or "text/html" in content_type:
        raise HTTPException(
            status_code=502,
            detail="구글시트를 읽을 수 없습니다. 시트가 '링크가 있는 모든 사용자'에게 공개되어 있는지 확인하거나 CSV 파일 업로드를 사용하세요.",
        )
    return resp.text


def _find_column(headers: List[str], keywords: Tuple[str, ...]) -> Optional[int]:
    for index, header in enumerate(headers):
        normalized = header.strip().lower()
        if not normalized:
            continue
        for keyword in keywords:
            if keyword in normalized:
                return index
    return None


def _parse_member_rows(csv_text: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """CSV 텍스트를 회원 행 목록으로 파싱합니다. (rows, errors) 반환."""
    reader = csv.reader(io.StringIO(csv_text))
    raw_rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not raw_rows:
        raise HTTPException(status_code=400, detail="시트에 데이터가 없습니다.")

    # 헤더 행 탐색: 이름/학번 컬럼을 모두 찾을 수 있는 첫 행 (상위 5행 내)
    header_index = -1
    name_col = sid_col = major_col = gen_col = None
    for i, row in enumerate(raw_rows[:5]):
        n = _find_column(row, _NAME_HEADERS)
        s = _find_column(row, _STUDENT_ID_HEADERS)
        if n is not None and s is not None:
            header_index, name_col, sid_col = i, n, s
            major_col = _find_column(row, _MAJOR_HEADERS)
            gen_col = _find_column(row, _GENERATION_HEADERS)
            break
    if header_index < 0:
        raise HTTPException(
            status_code=400,
            detail="헤더에서 '이름'과 '학번' 컬럼을 찾지 못했습니다. 시트 첫 행에 컬럼명이 있는지 확인하세요.",
        )

    rows: List[Dict[str, str]] = []
    errors: List[str] = []
    seen_student_ids: set = set()

    for line_no, row in enumerate(raw_rows[header_index + 1 :], start=header_index + 2):
        def cell(col: Optional[int]) -> str:
            if col is None or col >= len(row):
                return ""
            return row[col].strip()

        name = cell(name_col)
        student_id = re.sub(r"\s", "", cell(sid_col))
        if not name and not student_id:
            continue
        if not name:
            errors.append(f"{line_no}행: 이름이 비어 있습니다.")
            continue
        if not STUDENT_ID_PATTERN.match(student_id):
            errors.append(f"{line_no}행({name}): 학번은 8자리 숫자여야 합니다. (입력값: '{student_id}')")
            continue
        if student_id in seen_student_ids:
            errors.append(f"{line_no}행({name}): 학번 {student_id}이(가) 시트에 중복되어 있습니다.")
            continue
        seen_student_ids.add(student_id)

        rows.append(
            {
                "name": name,
                "student_id": student_id,
                "major": cell(major_col),
                "generation": cell(gen_col),
            }
        )

    return rows, errors


@router.post("/sync", response_model=MemberSyncResult)
def sync_members(payload: MemberSyncRequest, _: str = Depends(require_admin)):
    """멤버 시트를 읽어 회원 DB를 동기화합니다.

    - csv_text가 오면 CSV를 사용하고, 없으면 구글시트(요청 sheet_url → 서버 기본값 순)를 읽습니다.
    - 신규 회원: {학번}@도메인 가상 이메일로 auth 계정 생성, 초기 비밀번호 = 학번,
      최초 로그인 시 비밀번호 변경 필요 플래그 설정.
    - 기존 회원(학번 기준): 이름/학과/기수만 갱신. 시트에 없는 회원은 건드리지 않습니다.
    """
    csv_text = (payload.csv_text or "").strip()
    if csv_text:
        source = "csv"
    else:
        sheet_url = (payload.sheet_url or MEMBER_SHEET_URL or "").strip()
        if not sheet_url:
            raise HTTPException(
                status_code=400,
                detail="구글시트 URL이 설정되어 있지 않습니다. CSV 파일을 업로드하거나 MEMBER_SHEET_URL을 설정하세요.",
            )
        csv_text = _fetch_sheet_csv(sheet_url)
        source = "sheet"

    rows, errors = _parse_member_rows(csv_text)

    sb = get_supabase()
    existing_resp = (
        sb.table("users").select("id,student_id,name,major,generation,email").execute()
    )
    existing_by_sid: Dict[str, dict] = {}
    for user in existing_resp.data or []:
        sid = (user.get("student_id") or "").strip()
        if sid:
            existing_by_sid[sid] = user

    created = updated = unchanged = 0
    created_names: List[str] = []

    for row in rows:
        sid = row["student_id"]
        existing = existing_by_sid.get(sid)

        if existing:
            changes = {}
            for field in ("name", "major", "generation"):
                if row[field] and row[field] != (existing.get(field) or ""):
                    changes[field] = row[field]
            if changes:
                try:
                    sb.table("users").update(changes).eq("id", existing["id"]).execute()
                    updated += 1
                except Exception as exc:
                    errors.append(f"{row['name']}({sid}): 프로필 갱신 실패 - {exc}")
            else:
                unchanged += 1
            continue

        try:
            create_resp = sb.auth.admin.create_user(
                {
                    "email": _member_email(sid),
                    "password": sid,
                    "email_confirm": True,
                    "user_metadata": {
                        "name": row["name"],
                        "student_id": sid,
                        "sid": sid,
                        "major": row["major"] or "미입력",
                        "generation": row["generation"],
                    },
                }
            )
            user_id = create_resp.user.id if create_resp and create_resp.user else None
            if not user_id:
                raise RuntimeError("auth 계정 생성 응답에 사용자 ID가 없습니다.")
            # auth.users 트리거가 public.users 행을 만들지만, 트리거 버전에 따라
            # 일부 필드(기수 등)가 누락될 수 있어 프로필을 여기서 직접 확정한다.
            profile = {
                "name": row["name"],
                "student_id": sid,
                "major": row["major"] or "미입력",
                "generation": row["generation"],
                "must_change_password": True,
            }
            sb.table("users").update(profile).eq("id", user_id).execute()
            created += 1
            created_names.append(row["name"])
        except Exception as exc:
            errors.append(f"{row['name']}({sid}): 계정 생성 실패 - {exc}")

    return MemberSyncResult(
        source=source,
        total_rows=len(rows),
        created=created,
        updated=updated,
        unchanged=unchanged,
        created_names=created_names,
        errors=errors,
    )


@router.get("", response_model=List[MemberProfile])
def list_members(_: str = Depends(require_admin)):
    sb = get_supabase()
    resp = (
        sb.table("users")
        .select("id,email,name,student_id,major,generation,role,must_change_password")
        .order("name")
        .execute()
    )
    return resp.data or []


@router.post("/{user_id}/reset-password")
def reset_member_password(user_id: str, _: str = Depends(require_admin)):
    """회원 비밀번호를 학번으로 초기화하고, 다음 로그인 시 변경을 강제합니다."""
    sb = get_supabase()
    resp = sb.table("users").select("student_id,name").eq("id", user_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    student_id = (resp.data[0].get("student_id") or "").strip()
    if len(student_id) < 6:
        raise HTTPException(status_code=400, detail="학번이 6자 미만이라 초기 비밀번호로 사용할 수 없습니다.")

    try:
        sb.auth.admin.update_user_by_id(user_id, {"password": student_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"비밀번호 초기화에 실패했습니다: {exc}")

    sb.table("users").update({"must_change_password": True}).eq("id", user_id).execute()
    return {"ok": True}


@router.get("/me", response_model=MemberProfile)
def get_my_profile(user_id: str = Depends(require_auth)):
    sb = get_supabase()
    resp = (
        sb.table("users")
        .select("id,email,name,student_id,major,generation,role,must_change_password")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="회원 정보를 찾을 수 없습니다.")
    return resp.data[0]


@router.get("/me/debates", response_model=List[MyDebateItem])
def list_my_debates(user_id: str = Depends(require_auth)):
    sb = get_supabase()
    part_resp = (
        sb.table("debate_participants")
        .select("debate_id,side")
        .eq("user_id", user_id)
        .execute()
    )
    participations = part_resp.data or []
    if not participations:
        return []

    side_by_debate = {p["debate_id"]: p["side"] for p in participations}
    debate_resp = (
        sb.table("debates")
        .select("id,topic_text,debate_date,debate_type,winner_side")
        .in_("id", list(side_by_debate.keys()))
        .order("debate_date", desc=True)
        .execute()
    )

    items: List[MyDebateItem] = []
    for debate in debate_resp.data or []:
        side = "con" if side_by_debate.get(debate["id"]) == "con" else "pro"
        winner = debate.get("winner_side")
        if winner not in ("pro", "con"):
            result = "pending"
        elif winner == side:
            result = "win"
        else:
            result = "loss"
        items.append(
            MyDebateItem(
                debate_id=debate["id"],
                topic=debate.get("topic_text") or "",
                date=debate.get("debate_date"),
                debate_type=debate.get("debate_type") or "자유토론",
                side=side,
                winner_side=winner if winner in ("pro", "con") else None,
                result=result,
            )
        )
    return items


@router.get("/stats", response_model=List[MemberStatsRow])
def member_stats():
    """회원별 통산 전적. winner_side가 기록된 토론만 승/패로 집계합니다."""
    sb = get_supabase()
    users_resp = sb.table("users").select("id,name,generation,major,role").execute()
    parts_resp = (
        sb.table("debate_participants")
        .select("user_id,debate_id,side")
        .not_.is_("user_id", "null")
        .execute()
    )
    debates_resp = sb.table("debates").select("id,winner_side").execute()

    winner_by_debate = {d["id"]: d.get("winner_side") for d in debates_resp.data or []}

    stats: Dict[str, MemberStatsRow] = {}
    for user in users_resp.data or []:
        stats[user["id"]] = MemberStatsRow(
            user_id=user["id"],
            name=(user.get("name") or "").strip() or "이름 미입력",
            generation=(user.get("generation") or "").strip(),
            major=(user.get("major") or "").strip(),
        )

    for part in parts_resp.data or []:
        row = stats.get(part.get("user_id") or "")
        if row is None:
            continue
        row.total += 1
        winner = winner_by_debate.get(part.get("debate_id"))
        if winner not in ("pro", "con"):
            continue
        if winner == part.get("side"):
            row.wins += 1
        else:
            row.losses += 1

    result = list(stats.values())
    for row in result:
        decided = row.wins + row.losses
        row.win_rate = round(row.wins / decided, 4) if decided > 0 else 0.0

    result.sort(key=lambda r: (-r.wins, -r.win_rate, -r.total, r.name))
    return result
