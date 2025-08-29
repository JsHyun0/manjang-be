from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.db import get_supabase
from app.models import Reservation, ReservationCreate, ReservationCreateResponse


router = APIRouter()


@router.get("", response_model=List[Reservation])
def list_reservations(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    date_eq: Optional[date] = Query(default=None, alias="date"),
):
    sb = get_supabase()
    query = sb.table("reservations").select("*")
    if date_eq is not None:
        # 하루 단위 범위로 변환
        day_start = f"{date_eq.isoformat()}T00:00:00Z"
        day_end = f"{date_eq.isoformat()}T23:59:59Z"
        query = query.gte("starts_at", day_start).lte("ends_at", day_end)
    if start is not None:
        query = query.gte("ends_at", start.isoformat())
    if end is not None:
        query = query.lte("starts_at", end.isoformat())
    resp = query.order("starts_at", desc=False).execute()
    return resp.data or []


def _check_overlap(sb, starts_at: datetime, ends_at: datetime) -> bool:
    overlap = (
        sb.table("reservations")
        .select("id")
        .lt("starts_at", ends_at.isoformat())
        .gt("ends_at", starts_at.isoformat())
        .limit(1)
        .execute()
    )
    return bool(overlap.data)


def _warn_opponent_same_debate(sb, debate_id: UUID, reserved_by: Optional[UUID], starts_at: datetime, ends_at: datetime) -> bool:
    # 본인 side 조회
    if not reserved_by:
        # 익명 예약의 경우 상대 경고 로직을 건너뜀
        return False

    my_side_resp = (
        sb.table("debate_participants")
        .select("side")
        .eq("debate_id", str(debate_id))
        .eq("user_id", str(reserved_by))
        .single()
        .execute()
    )
    if not my_side_resp.data:
        # 토론 참가자가 아니면 유효성 위반
        raise HTTPException(status_code=400, detail="해당 토론 참가자만 선택할 수 있습니다.")
    my_side = my_side_resp.data["side"]
    opponent_side = "con" if my_side == "pro" else "pro"

    # 같은 시간대 동일 토론의 상대팀 예약 존재 여부
    other_resps = (
        sb.table("reservations")
        .select("id, reserved_by")
        .eq("debate_id", str(debate_id))
        .lt("starts_at", ends_at.isoformat())
        .gt("ends_at", starts_at.isoformat())
        .execute()
    )
    if not other_resps.data:
        return False

    # 상대팀인지 확인
    user_ids = [row["reserved_by"] for row in other_resps.data]
    if not user_ids:
        return False

    parts = (
        sb.table("debate_participants")
        .select("user_id, side")
        .eq("debate_id", debate_id)
        .in_("user_id", user_ids)
        .execute()
    )
    for p in parts.data or []:
        if p["side"] == opponent_side:
            return True
    return False


@router.post("", response_model=ReservationCreateResponse)
def create_reservation(payload: ReservationCreate):
    sb = get_supabase()

    # 시간 겹침 검사 (단일 방)
    # if _check_overlap(sb, payload.starts_at, payload.ends_at):
        # raise HTTPException(status_code=409, detail="이미 해당 시간대에 예약이 있습니다.")

    warn_opponent = False
    if payload.debate_id:
        warn_opponent = _warn_opponent_same_debate(
            sb,
            payload.debate_id,
            payload.reserved_by,
            payload.starts_at,
            payload.ends_at,
        )

    # null/None 값 제외 + datetime 등을 JSON 직렬화 가능한 값으로 변환
    payload_dict = payload.model_dump(mode="json", exclude_none=True)
    resp = sb.table("reservations").insert(payload_dict).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create reservation")
    created = resp.data[0] if isinstance(resp.data, list) else resp.data
    return {"reservation": created, "warn_opponent_booked": warn_opponent}


@router.delete("/{reservation_id}")
def cancel_reservation(reservation_id: str):
    sb = get_supabase()
    resp = sb.table("reservations").delete().eq("id", reservation_id).execute()
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return {"ok": True}


