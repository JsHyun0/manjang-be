from datetime import date, datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field
from uuid import UUID


# -----------------------------
# Debates
# -----------------------------
class DebateBase(BaseModel):
    topic_text: str
    debate_date: date
    winner_side: Optional[Literal["pro", "con"]] = None
    notes: Optional[str] = None


class DebateCreate(DebateBase):
    pass


class Debate(DebateBase):
    id: str
    created_by: Optional[str] = None


class DebateParticipant(BaseModel):
    id: Optional[int] = None
    debate_id: str
    user_id: str
    side: Literal["pro", "con"]


# -----------------------------
# Reservations (단일 방)
# -----------------------------
class ReservationBase(BaseModel):
    reserved_by: Optional[UUID] = None
    reserved_by_name: Optional[str] = None
    title: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    debate_id: Optional[UUID] = None


class ReservationCreate(ReservationBase):
    pass


class Reservation(ReservationBase):
    id: str


class ReservationCreateResponse(BaseModel):
    reservation: Reservation
    warn_opponent_booked: bool = False


# -----------------------------
# Legacy Records (for /records router compatibility)
# -----------------------------
class DebateRecordBase(BaseModel):
    title: str
    category: str
    date: date
    summary: str
    keyPoints: List[str] = Field(default_factory=list)
    conclusion: str
    participants: int
    participantNames: List[str] = Field(default_factory=list)


class DebateRecordCreate(DebateRecordBase):
    pass


class DebateRecord(DebateRecordBase):
    id: str


