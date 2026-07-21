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
    user_id: Optional[str] = None
    participant_name: Optional[str] = None
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
    allow_simultaneous: bool = False


class ReservationCreate(ReservationBase):
    pass


class Reservation(ReservationBase):
    id: str


class ReservationCreateResponse(BaseModel):
    reservation: Reservation
    warn_opponent_booked: bool = False


# 부분 수정을 위한 모델
class ReservationUpdate(BaseModel):
    reserved_by_name: Optional[str] = None
    title: Optional[str] = None


# -----------------------------
# Members (사전 등록 회원 시스템)
# -----------------------------
class MemberSyncRequest(BaseModel):
    sheet_url: Optional[str] = None
    csv_text: Optional[str] = None


class MemberSyncResult(BaseModel):
    source: Literal["sheet", "csv"]
    total_rows: int
    created: int
    updated: int
    unchanged: int
    created_names: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class MemberProfile(BaseModel):
    id: str
    email: str
    name: str
    student_id: str
    major: str = ""
    generation: str = ""
    role: str = "member"
    must_change_password: bool = False


class MyDebateItem(BaseModel):
    debate_id: str
    topic: str
    date: date
    debate_type: str = "자유토론"
    side: Literal["pro", "con"]
    winner_side: Optional[Literal["pro", "con"]] = None
    result: Literal["win", "loss", "pending"]


class MemberStatsRow(BaseModel):
    user_id: str
    name: str
    generation: str = ""
    major: str = ""
    wins: int = 0
    losses: int = 0
    total: int = 0
    win_rate: float = 0.0


class LoginLookupRequest(BaseModel):
    name: str
    student_id: str


class LoginLookupResponse(BaseModel):
    email: str


class PasswordChangeRequest(BaseModel):
    new_password: str


# -----------------------------
# Event tournaments
# -----------------------------
TournamentStatus = Literal["draft", "open", "ongoing", "completed"]
TournamentStage = Literal["group", "final"]


class TournamentBase(BaseModel):
    title: str
    topic: str = ""
    description: str = ""
    debate_format: str = "자유토론"
    starts_on: date
    ends_on: date
    venue: str = ""
    status: TournamentStatus = "draft"
    points_per_win: int = Field(default=1, ge=1, le=10)


class TournamentCreate(TournamentBase):
    pass


class TournamentUpdate(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    debate_format: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    venue: Optional[str] = None
    status: Optional[TournamentStatus] = None
    points_per_win: Optional[int] = Field(default=None, ge=1, le=10)


class TournamentSummary(TournamentBase):
    id: str
    team_count: int = 0
    match_count: int = 0
    completed_match_count: int = 0


class TournamentTeamMemberInput(BaseModel):
    user_id: str
    experience_score: int = Field(default=1, ge=1, le=3)


class TournamentTeamInput(BaseModel):
    client_key: str
    name: str
    group_name: str
    members: List[TournamentTeamMemberInput] = Field(default_factory=list)


class TournamentMatchInput(BaseModel):
    stage: TournamentStage = "group"
    round_label: str = ""
    starts_at: datetime
    venue: str = ""
    team_a_key: Optional[str] = None
    team_b_key: Optional[str] = None
    team_a_source_group: Optional[str] = None
    team_b_source_group: Optional[str] = None
    winner_team_key: Optional[str] = None
    team_a_score: Optional[float] = None
    team_b_score: Optional[float] = None
    status: Literal["scheduled", "completed"] = "scheduled"
    notes: str = ""


class TournamentSetup(BaseModel):
    teams: List[TournamentTeamInput] = Field(default_factory=list)
    matches: List[TournamentMatchInput] = Field(default_factory=list)


class TournamentMatchResult(BaseModel):
    team_a_score: float = Field(ge=0)
    team_b_score: float = Field(ge=0)
    winner_team_id: Optional[str] = None


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
