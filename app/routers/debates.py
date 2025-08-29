from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_supabase
from app.models import Debate, DebateCreate, DebateParticipant


router = APIRouter()


@router.get("", response_model=List[Debate])
def list_debates(year: Optional[int] = Query(default=None)):
    sb = get_supabase()
    query = sb.table("debates").select("*")
    if year is not None:
        # Supabase는 SQL 함수 사용 대신 필터로 처리 어려움 → 범위로 대체
        query = (
            query
            .gte("debate_date", f"{year}-01-01")
            .lte("debate_date", f"{year}-12-31")
        )
    resp = query.order("debate_date", desc=True).execute()
    return resp.data or []


@router.post("", response_model=Debate)
def create_debate(payload: DebateCreate):
    sb = get_supabase()
    resp = (
        sb.table("debates")
        .insert(payload.model_dump())
        .select("*")
        .single()
        .execute()
    )
    if resp.data is None:
        raise HTTPException(status_code=500, detail="Failed to create debate")
    return resp.data


@router.get("/{debate_id}", response_model=Debate)
def get_debate(debate_id: str):
    sb = get_supabase()
    resp = sb.table("debates").select("*").eq("id", debate_id).single().execute()
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    return resp.data


@router.post("/{debate_id}/participants", response_model=DebateParticipant)
def add_participant(debate_id: str, participant: DebateParticipant):
    if participant.debate_id != debate_id:
        raise HTTPException(status_code=400, detail="debate_id mismatch")
    sb = get_supabase()
    # unique(debate_id,user_id) 보장
    existing = (
        sb.table("debate_participants")
        .select("id")
        .eq("debate_id", debate_id)
        .eq("user_id", participant.user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        # 이미 있으면 side만 갱신 가능
        updated = (
            sb.table("debate_participants")
            .update({"side": participant.side})
            .eq("debate_id", debate_id)
            .eq("user_id", participant.user_id)
            .select("*")
            .single()
            .execute()
        )
        return updated.data

    resp = (
        sb.table("debate_participants")
        .insert({
            "debate_id": debate_id,
            "user_id": participant.user_id,
            "side": participant.side,
        })
        .select("*")
        .single()
        .execute()
    )
    if resp.data is None:
        raise HTTPException(status_code=500, detail="Failed to add participant")
    return resp.data


@router.delete("/{debate_id}/participants/{user_id}")
def remove_participant(debate_id: str, user_id: str):
    sb = get_supabase()
    resp = (
        sb.table("debate_participants")
        .delete()
        .eq("debate_id", debate_id)
        .eq("user_id", user_id)
        .execute()
    )
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"ok": True}


@router.post("/{debate_id}/winner")
def set_winner(debate_id: str, winner_side: str):
    if winner_side not in ("pro", "con"):
        raise HTTPException(status_code=400, detail="winner_side must be 'pro' or 'con'")
    sb = get_supabase()
    resp = (
        sb.table("debates")
        .update({"winner_side": winner_side})
        .eq("id", debate_id)
        .select("*")
        .single()
        .execute()
    )
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    return resp.data


