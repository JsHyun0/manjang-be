from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import is_admin_user, require_auth
from app.db import get_supabase
from app.models import (
    Reservation,
    ReservationCreate,
    ReservationCreateResponse,
    ReservationUpdate,
)


router = APIRouter()
RESERVATION_SELECT_COLUMNS = "id,reserved_by,reserved_by_name,title,starts_at,ends_at,debate_id,allow_simultaneous"


@router.get("", response_model=List[Reservation])
def list_reservations(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    date_eq: Optional[date] = Query(default=None, alias="date"),
):
    sb = get_supabase()
    query = sb.table("reservations").select(RESERVATION_SELECT_COLUMNS)
    if date_eq is not None:
        start = date_eq
        end = date_eq + timedelta(days=1)

    if start is not None:
        start_at = f"{start.isoformat()}T00:00:00Z"
        query = query.gte("starts_at", start_at)

    if end is not None:
        end_exclusive = f"{end.isoformat()}T00:00:00Z"
        query = query.lt("starts_at", end_exclusive)

    resp = query.order("starts_at", desc=False).execute()
    return resp.data or []


@router.get("/month", response_model=List[Reservation])
def list_reservations_around_month(date_eq: date = Query(alias="date")):
    sb = get_supabase()
    year = date_eq.year
    month = date_eq.month

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    prev_start = datetime(prev_year, prev_month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if next_month == 12:
        after_next_year, after_next_month = next_year + 1, 1
    else:
        after_next_year, after_next_month = next_year, next_month + 1
    end_exclusive = datetime(after_next_year, after_next_month, 1, 0, 0, 0, tzinfo=timezone.utc)

    query = (
        sb.table("reservations")
        .select(RESERVATION_SELECT_COLUMNS)
        .gte("starts_at", prev_start.isoformat())
        .lt("starts_at", end_exclusive.isoformat())
        .order("starts_at", desc=False)
    )
    resp = query.execute()
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
    if not reserved_by:
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
        raise HTTPException(status_code=400, detail="해당 토론 참가자만 선택할 수 있습니다.")
    my_side = my_side_resp.data["side"]
    opponent_side = "con" if my_side == "pro" else "pro"

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
def create_reservation(payload: ReservationCreate, user_id: str = Depends(require_auth)):
    sb = get_supabase()

    # 본인 명의 예약인지 확인 (admin은 타인 대리 예약 가능)
    if payload.reserved_by is not None and str(payload.reserved_by) != user_id:
        if not is_admin_user(user_id):
            raise HTTPException(status_code=403, detail="본인 명의로만 예약할 수 있습니다.")

    # reserved_by 미설정 시 인증된 사용자로 자동 설정
    if payload.reserved_by is None:
        payload = payload.model_copy(update={"reserved_by": UUID(user_id)})

    # 동시 예약 허용 검사 (최대 2팀)
    overlap_resp = (
        sb.table("reservations")
        .select("id, allow_simultaneous")
        .lt("starts_at", payload.ends_at.isoformat())
        .gt("ends_at", payload.starts_at.isoformat())
        .execute()
    )
    existing = overlap_resp.data or []

    if len(existing) >= 2:
        raise HTTPException(status_code=409, detail="이미 해당 시간대에 최대 예약 인원(2팀)이 차 있습니다.")

    if len(existing) == 1:
        existing_allows = existing[0].get("allow_simultaneous", False)
        if not existing_allows:
            raise HTTPException(status_code=409, detail="해당 시간대의 기존 예약이 동시 예약을 허용하지 않습니다.")
        if not payload.allow_simultaneous:
            raise HTTPException(status_code=409, detail="이미 예약된 시간대에는 동시 예약 허용이 필요합니다.")

    warn_opponent = False
    if payload.debate_id:
        warn_opponent = _warn_opponent_same_debate(
            sb,
            payload.debate_id,
            payload.reserved_by,
            payload.starts_at,
            payload.ends_at,
        )

    payload_dict = payload.model_dump(mode="json", exclude_none=True)
    resp = sb.table("reservations").insert(payload_dict).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create reservation")
    created = resp.data[0] if isinstance(resp.data, list) else resp.data
    return {"reservation": created, "warn_opponent_booked": warn_opponent}


@router.delete("/{reservation_id}")
def cancel_reservation(reservation_id: str, user_id: str = Depends(require_auth)):
    sb = get_supabase()
    exists = (
        sb.table("reservations").select("id,reserved_by").eq("id", reservation_id).limit(1).execute()
    )
    if not exists.data:
        raise HTTPException(status_code=404, detail="Reservation not found")

    reserved_by = str(exists.data[0].get("reserved_by") or "")
    if reserved_by != user_id and not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="본인의 예약만 취소할 수 있습니다.")

    sb.table("reservations").delete().eq("id", reservation_id).execute()
    return {"ok": True, "id": reservation_id}


@router.patch("/{reservation_id}", response_model=Reservation)
def update_reservation(reservation_id: str, payload: ReservationUpdate, user_id: str = Depends(require_auth)):
    sb = get_supabase()

    exists = (
        sb.table("reservations").select("id,reserved_by").eq("id", reservation_id).limit(1).execute()
    )
    if not exists.data:
        raise HTTPException(status_code=404, detail="Reservation not found")

    reserved_by = str(exists.data[0].get("reserved_by") or "")
    if reserved_by != user_id and not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="본인의 예약만 수정할 수 있습니다.")

    update_dict = payload.model_dump(exclude_none=True)
    if not update_dict:
        return exists.data[0]

    sb.table("reservations").update(update_dict).eq("id", reservation_id).execute()
    # supabase-py 2.x는 update 후 select 체이닝을 지원하지 않으므로 별도 재조회
    row = sb.table("reservations").select("*").eq("id", reservation_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return row.data[0]
