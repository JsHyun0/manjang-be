from supabase import create_client, Client

from dotenv import load_dotenv
import os
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, require_env

load_dotenv()

# TTL 기반 싱글턴 캐시: 장기 HTTP/2 세션 이슈 완화 + 성능 유지
_SB_CLIENT: Optional[Client] = None
_SB_CREATED_AT: float = 0.0
_TTL_SECONDS: int = int(os.getenv("SUPABASE_CLIENT_TTL_SECONDS", "300"))  # 기본 5분


def _create_client() -> Client:
    url = SUPABASE_URL or require_env("SUPABASE_URL")
    key = SUPABASE_SERVICE_ROLE_KEY or require_env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def get_supabase() -> Client:
    global _SB_CLIENT, _SB_CREATED_AT
    now = time.time()
    if _SB_CLIENT is None or (now - _SB_CREATED_AT) > _TTL_SECONDS:
        _SB_CLIENT = _create_client()
        _SB_CREATED_AT = now
    return _SB_CLIENT



# -----------------------------
# Users - prototype helpers
# -----------------------------
def create_user(
    user_id: str,
    email: str,
    name: str,
    student_id: str,
    major: str,
) -> Dict[str, Any]:
    client = get_supabase()
    payload: Dict[str, Any] = {
        "id": user_id,
        "email": email,
        "name": name,
        "student_id": student_id,
        "major": major,
    }
    response = client.table("users").insert(payload).execute()
    return response.data[0] if response.data else {}


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    response = (
        client.table("users")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]
    return None


# -----------------------------
# Debates - prototype helpers
# -----------------------------
def create_debate(
    title: str,
    description: Optional[str] = None,
    scheduled_at: Optional[datetime] = None,
    status: str = "scheduled",
    created_by: Optional[str] = None,
    participants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    client = get_supabase()
    payload: Dict[str, Any] = {"title": title, "status": status}
    if description is not None:
        payload["description"] = description
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at.isoformat()
    if created_by is not None:
        payload["created_by"] = created_by
    if participants is not None:
        payload["participants"] = participants

    response = client.table("debates").insert(payload).execute()
    return response.data[0] if response.data else {}


def list_debates(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "scheduled_at",
    descending: bool = False,
) -> List[Dict[str, Any]]:
    client = get_supabase()
    query = client.table("debates").select("*")
    if status is not None:
        query = query.eq("status", status)
    query = query.order(order_by, desc=descending)
    # Supabase range is inclusive; end = offset + limit - 1
    response = query.range(offset, max(offset + limit - 1, offset)).execute()
    return response.data or []


def add_participant_to_debate(debate_id: str, participant_name: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    current = (
        client.table("debates").select("id, participants").eq("id", debate_id).limit(1).execute()
    )
    if not current.data:
        return None
    participants: List[str] = current.data[0].get("participants", []) or []
    if participant_name not in participants:
        participants.append(participant_name)
    client.table("debates").update({"participants": participants}).eq("id", debate_id).execute()
    refreshed = client.table("debates").select("*").eq("id", debate_id).limit(1).execute()
    return refreshed.data[0] if refreshed.data else None
