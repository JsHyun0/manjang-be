from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_supabase
from app.models import DebateRecord, DebateRecordCreate


router = APIRouter()


@router.get("", response_model=List[DebateRecord])
def list_records(
    search: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default="date-desc"),
):
    sb = get_supabase()
    query = sb.table("records").select("*")

    if category:
        query = query.eq("category", category)

    # 검색: 제목, 요약, 참가자 이름
    # Supabase에서 or 검색을 위해 filter string 사용
    if search:
        like = f"%{search}%"
        query = query.or_(
            f"title.ilike.{like},summary.ilike.{like},participantNames.cs.{{{search}}}"
        )

    # 정렬
    if sort == "date-asc":
        query = query.order("date", desc=False)
    elif sort == "participants-desc":
        query = query.order("participants", desc=True)
    elif sort == "title":
        query = query.order("title", desc=False)
    else:
        query = query.order("date", desc=True)

    resp = query.execute()
    data = resp.data or []
    return data


@router.post("", response_model=DebateRecord)
def create_record(payload: DebateRecordCreate):
    sb = get_supabase()
    # id는 DB에서 생성(UUID)한다고 가정
    resp = sb.table("records").insert(payload.model_dump()).select("*").single().execute()
    if resp.data is None:
        raise HTTPException(status_code=500, detail="Failed to create record")
    return resp.data


@router.put("/{record_id}", response_model=DebateRecord)
def update_record(record_id: str, payload: DebateRecordCreate):
    sb = get_supabase()
    resp = (
        sb.table("records")
        .update(payload.model_dump())
        .eq("id", record_id)
        .select("*")
        .single()
        .execute()
    )
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return resp.data


@router.delete("/{record_id}")
def delete_record(record_id: str):
    sb = get_supabase()
    resp = sb.table("records").delete().eq("id", record_id).execute()
    if resp.data is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True}


