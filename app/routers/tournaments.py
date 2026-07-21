from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin
from app.db import get_supabase
from app.models import (
    TournamentCreate,
    TournamentMatchResult,
    TournamentSetup,
    TournamentSummary,
    TournamentUpdate,
)

router = APIRouter()


def _clean_required(value: str, label: str) -> str:
    clean = value.strip()
    if not clean:
        raise HTTPException(status_code=400, detail=f"{label}을(를) 입력해주세요.")
    return clean


def _team_experience(team: dict) -> float:
    members = team.get("members") or []
    if members:
        return round(sum(float(member.get("experience_score") or 1) for member in members) / len(members), 2)
    return float(team.get("experience_score") or 0)


def _build_standings(event: dict, teams: List[dict], matches: List[dict]) -> List[dict]:
    points_per_win = int(event.get("points_per_win") or 1)
    teams_by_group: Dict[str, List[dict]] = defaultdict(list)
    for team in teams:
        teams_by_group[team.get("group_name") or "미배정"].append(team)

    result: List[dict] = []
    for group_name in sorted(teams_by_group.keys()):
        group_teams = teams_by_group[group_name]
        rows: Dict[str, dict] = {}
        for team in group_teams:
            rows[team["id"]] = {
                "team_id": team["id"],
                "team_name": team["name"],
                "group_name": group_name,
                "played": 0,
                "wins": 0,
                "losses": 0,
                "points": 0,
                "head_to_head_wins": 0,
                "experience_score": _team_experience(team),
            }

        completed = []
        for match in matches:
            if match.get("stage") != "group" or match.get("group_name") != group_name:
                continue
            if match.get("status") != "completed" or not match.get("winner_team_id"):
                continue
            team_a_id = match.get("team_a_id")
            team_b_id = match.get("team_b_id")
            if team_a_id not in rows or team_b_id not in rows:
                continue
            completed.append(match)
            winner_id = match["winner_team_id"]
            loser_id = team_b_id if winner_id == team_a_id else team_a_id
            rows[team_a_id]["played"] += 1
            rows[team_b_id]["played"] += 1
            rows[winner_id]["wins"] += 1
            rows[winner_id]["points"] += points_per_win
            rows[loser_id]["losses"] += 1

        # 같은 승점을 가진 팀끼리의 미니리그 승수를 상대 전적 값으로 사용한다.
        tied_by_points: Dict[int, List[str]] = defaultdict(list)
        for row in rows.values():
            tied_by_points[row["points"]].append(row["team_id"])
        for tied_ids in tied_by_points.values():
            if len(tied_ids) < 2:
                continue
            tied_set = set(tied_ids)
            for match in completed:
                if match.get("team_a_id") in tied_set and match.get("team_b_id") in tied_set:
                    rows[match["winner_team_id"]]["head_to_head_wins"] += 1

        ordered = sorted(
            rows.values(),
            key=lambda row: (
                -row["points"],
                -row["head_to_head_wins"],
                row["experience_score"],
                row["team_name"],
            ),
        )
        for index, row in enumerate(ordered, start=1):
            row["rank"] = index
            result.append(row)
    return result


def _event_snapshot(event_id: str) -> dict:
    sb = get_supabase()
    event_resp = sb.table("tournaments").select("*").eq("id", event_id).limit(1).execute()
    if not event_resp.data:
        raise HTTPException(status_code=404, detail="대회를 찾을 수 없습니다.")
    event = event_resp.data[0]

    team_resp = (
        sb.table("tournament_teams")
        .select("*")
        .eq("tournament_id", event_id)
        .order("group_name")
        .order("seed")
        .execute()
    )
    teams = team_resp.data or []
    team_by_id = {team["id"]: team for team in teams}

    if teams:
        member_resp = (
            sb.table("tournament_team_members")
            .select("id,team_id,user_id,experience_score,users(id,name,student_id,major,generation)")
            .in_("team_id", list(team_by_id.keys()))
            .execute()
        )
        for member in member_resp.data or []:
            profile = member.pop("users", None) or {}
            member["name"] = profile.get("name") or "회원"
            member["student_id"] = profile.get("student_id") or ""
            member["major"] = profile.get("major") or ""
            member["generation"] = profile.get("generation") or ""
            team = team_by_id.get(member.get("team_id"))
            if team is not None:
                team.setdefault("members", []).append(member)
    for team in teams:
        team.setdefault("members", [])
        team["experience_score"] = _team_experience(team)

    match_resp = (
        sb.table("tournament_matches")
        .select("*")
        .eq("tournament_id", event_id)
        .order("starts_at")
        .execute()
    )
    matches = match_resp.data or []
    standings = _build_standings(event, teams, matches)
    winner_by_group = {
        row["group_name"]: row["team_id"] for row in standings if row.get("rank") == 1
    }

    for match in matches:
        resolved_a = match.get("team_a_id") or winner_by_group.get(match.get("team_a_source_group"))
        resolved_b = match.get("team_b_id") or winner_by_group.get(match.get("team_b_source_group"))
        match["resolved_team_a_id"] = resolved_a
        match["resolved_team_b_id"] = resolved_b
        match["team_a_name"] = (
            (team_by_id.get(resolved_a) or {}).get("name")
            or (f"{match.get('team_a_source_group')}조 1위" if match.get("team_a_source_group") else "미정")
        )
        match["team_b_name"] = (
            (team_by_id.get(resolved_b) or {}).get("name")
            or (f"{match.get('team_b_source_group')}조 1위" if match.get("team_b_source_group") else "미정")
        )
        match["winner_team_name"] = (team_by_id.get(match.get("winner_team_id")) or {}).get("name")

    event["teams"] = teams
    event["matches"] = matches
    event["standings"] = standings
    event["progress"] = {
        "total": len(matches),
        "completed": sum(1 for match in matches if match.get("status") == "completed"),
    }
    return event


@router.get("", response_model=List[TournamentSummary])
def list_tournaments():
    sb = get_supabase()
    events_resp = sb.table("tournaments").select("*").order("starts_on", desc=True).execute()
    events = events_resp.data or []
    if not events:
        return []

    event_ids = [event["id"] for event in events]
    teams_resp = sb.table("tournament_teams").select("tournament_id").in_("tournament_id", event_ids).execute()
    matches_resp = (
        sb.table("tournament_matches")
        .select("tournament_id,status")
        .in_("tournament_id", event_ids)
        .execute()
    )
    team_counts: Dict[str, int] = defaultdict(int)
    match_counts: Dict[str, int] = defaultdict(int)
    completed_counts: Dict[str, int] = defaultdict(int)
    for row in teams_resp.data or []:
        team_counts[row["tournament_id"]] += 1
    for row in matches_resp.data or []:
        event_id = row["tournament_id"]
        match_counts[event_id] += 1
        if row.get("status") == "completed":
            completed_counts[event_id] += 1
    for event in events:
        event["team_count"] = team_counts[event["id"]]
        event["match_count"] = match_counts[event["id"]]
        event["completed_match_count"] = completed_counts[event["id"]]
    return events


@router.post("")
def create_tournament(payload: TournamentCreate, admin_id: str = Depends(require_admin)):
    if payload.ends_on < payload.starts_on:
        raise HTTPException(status_code=400, detail="종료일은 시작일보다 빠를 수 없습니다.")
    data = payload.model_dump(mode="json")
    data["title"] = _clean_required(payload.title, "대회명")
    data["created_by"] = admin_id
    sb = get_supabase()
    resp = sb.table("tournaments").insert(data).execute()
    created = (resp.data or [None])[0]
    if not created:
        raise HTTPException(status_code=500, detail="대회를 만들지 못했습니다.")
    return _event_snapshot(created["id"])


@router.get("/{event_id}")
def get_tournament(event_id: str):
    return _event_snapshot(event_id)


@router.patch("/{event_id}")
def update_tournament(event_id: str, payload: TournamentUpdate, _: str = Depends(require_admin)):
    changes = payload.model_dump(exclude_none=True, mode="json")
    if "title" in changes:
        changes["title"] = _clean_required(changes["title"], "대회명")
    starts_on = changes.get("starts_on")
    ends_on = changes.get("ends_on")
    if starts_on and ends_on and ends_on < starts_on:
        raise HTTPException(status_code=400, detail="종료일은 시작일보다 빠를 수 없습니다.")
    if changes:
        get_supabase().table("tournaments").update(changes).eq("id", event_id).execute()
    return _event_snapshot(event_id)


@router.put("/{event_id}/setup")
def replace_tournament_setup(event_id: str, payload: TournamentSetup, _: str = Depends(require_admin)):
    _event_snapshot(event_id)
    keys = [team.client_key.strip() for team in payload.teams]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="팀 식별값이 비어 있거나 중복되었습니다.")
    if any(not team.name.strip() or not team.group_name.strip() for team in payload.teams):
        raise HTTPException(status_code=400, detail="모든 팀의 팀명과 조를 입력해주세요.")
    known_keys = set(keys)
    for match in payload.matches:
        if match.team_a_key and match.team_a_key not in known_keys:
            raise HTTPException(status_code=400, detail="경기에서 존재하지 않는 팀을 참조하고 있습니다.")
        if match.team_b_key and match.team_b_key not in known_keys:
            raise HTTPException(status_code=400, detail="경기에서 존재하지 않는 팀을 참조하고 있습니다.")
        if match.winner_team_key and match.winner_team_key not in known_keys:
            raise HTTPException(status_code=400, detail="경기 승리 팀이 존재하지 않는 팀을 참조하고 있습니다.")
        if not (match.team_a_key or match.team_a_source_group):
            raise HTTPException(status_code=400, detail="경기 A팀 또는 진출 조건을 지정해주세요.")
        if not (match.team_b_key or match.team_b_source_group):
            raise HTTPException(status_code=400, detail="경기 B팀 또는 진출 조건을 지정해주세요.")

    member_ids = [member.user_id for team in payload.teams for member in team.members]
    if len(member_ids) != len(set(member_ids)):
        raise HTTPException(status_code=400, detail="한 참가자를 여러 팀에 중복 등록할 수 없습니다.")

    sb = get_supabase()
    old_teams = sb.table("tournament_teams").select("id").eq("tournament_id", event_id).execute()
    old_team_ids = [row["id"] for row in old_teams.data or []]
    sb.table("tournament_matches").delete().eq("tournament_id", event_id).execute()
    if old_team_ids:
        sb.table("tournament_team_members").delete().in_("team_id", old_team_ids).execute()
    sb.table("tournament_teams").delete().eq("tournament_id", event_id).execute()

    team_id_by_key: Dict[str, str] = {}
    team_payloads = [
        {
            "tournament_id": event_id,
            "name": team.name.strip(),
            "group_name": team.group_name.strip(),
            "seed": index,
            "experience_score": round(
                sum(member.experience_score for member in team.members) / len(team.members), 2
            ) if team.members else 0,
            "client_key": team.client_key,
        }
        for index, team in enumerate(payload.teams)
    ]
    if team_payloads:
        inserted = sb.table("tournament_teams").insert(team_payloads).execute()
        team_id_by_key = {row["client_key"]: row["id"] for row in inserted.data or []}

    member_payloads = []
    for team in payload.teams:
        team_id = team_id_by_key.get(team.client_key)
        if not team_id:
            continue
        for member in team.members:
            member_payloads.append(
                {
                    "team_id": team_id,
                    "user_id": member.user_id,
                    "experience_score": member.experience_score,
                }
            )
    if member_payloads:
        sb.table("tournament_team_members").insert(member_payloads).execute()

    match_payloads = []
    group_by_key = {team.client_key: team.group_name.strip() for team in payload.teams}
    for match in payload.matches:
        team_a_id = team_id_by_key.get(match.team_a_key or "")
        team_b_id = team_id_by_key.get(match.team_b_key or "")
        match_payloads.append(
            {
                "tournament_id": event_id,
                "stage": match.stage,
                "group_name": group_by_key.get(match.team_a_key or "") if match.stage == "group" else None,
                "round_label": match.round_label.strip(),
                "starts_at": match.starts_at.isoformat(),
                "venue": match.venue.strip(),
                "team_a_id": team_a_id,
                "team_b_id": team_b_id,
                "team_a_source_group": match.team_a_source_group,
                "team_b_source_group": match.team_b_source_group,
                "winner_team_id": team_id_by_key.get(match.winner_team_key or ""),
                "team_a_score": match.team_a_score,
                "team_b_score": match.team_b_score,
                "status": match.status,
                "notes": match.notes.strip(),
            }
        )
    if match_payloads:
        sb.table("tournament_matches").insert(match_payloads).execute()
    return _event_snapshot(event_id)


@router.patch("/{event_id}/matches/{match_id}/result")
def set_match_result(
    event_id: str,
    match_id: str,
    payload: TournamentMatchResult,
    _: str = Depends(require_admin),
):
    snapshot = _event_snapshot(event_id)
    match = next((item for item in snapshot["matches"] if item["id"] == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")
    team_a_id = match.get("resolved_team_a_id")
    team_b_id = match.get("resolved_team_b_id")
    if not team_a_id or not team_b_id:
        raise HTTPException(status_code=400, detail="진출 팀이 확정된 뒤 결과를 입력할 수 있습니다.")

    team_by_id = {team["id"]: team for team in snapshot["teams"]}
    if payload.team_a_score > payload.team_b_score:
        winner_id = team_a_id
    elif payload.team_b_score > payload.team_a_score:
        winner_id = team_b_id
    else:
        exp_a = _team_experience(team_by_id[team_a_id])
        exp_b = _team_experience(team_by_id[team_b_id])
        if exp_a < exp_b:
            winner_id = team_a_id
        elif exp_b < exp_a:
            winner_id = team_b_id
        elif payload.winner_team_id in (team_a_id, team_b_id):
            winner_id = payload.winner_team_id
        else:
            raise HTTPException(
                status_code=400,
                detail="점수와 평균 경력점수가 모두 같습니다. 승리 팀을 직접 선택해주세요.",
            )

    get_supabase().table("tournament_matches").update(
        {
            "team_a_id": team_a_id,
            "team_b_id": team_b_id,
            "team_a_score": payload.team_a_score,
            "team_b_score": payload.team_b_score,
            "winner_team_id": winner_id,
            "status": "completed",
        }
    ).eq("id", match_id).eq("tournament_id", event_id).execute()
    return _event_snapshot(event_id)
