from functools import lru_cache

from supabase import create_client, Client

from dotenv import load_dotenv
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

load_dotenv()

@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)



# -----------------------------
# Users - prototype helpers
# -----------------------------
def create_user(email: str, name: Optional[str] = None, sid: Optional[str] = None) -> Dict[str, Any]:
    client = get_supabase()
    payload: Dict[str, Any] = {"email": email}
    if name is not None:
        payload["name"] = name
    if sid is not None:
        payload["sid"] = sid
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
    updated = (
        client.table("debates")
        .update({"participants": participants})
        .eq("id", debate_id)
        .select("*")
        .limit(1)
        .execute()
    )
    return updated.data[0] if updated.data else None

