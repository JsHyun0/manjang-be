from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth
from app.db import get_supabase
from app.models import LoginLookupRequest, LoginLookupResponse, PasswordChangeRequest

router = APIRouter()


@router.post("/login-lookup", response_model=LoginLookupResponse)
def login_lookup(payload: LoginLookupRequest):
    """이름+학번으로 로그인용 이메일을 조회합니다. (Supabase 인증은 이메일 기반)"""
    name = payload.name.strip()
    student_id = payload.student_id.strip()
    if not name or not student_id:
        raise HTTPException(status_code=400, detail="이름과 학번을 모두 입력해주세요.")

    sb = get_supabase()
    resp = (
        sb.table("users")
        .select("email")
        .eq("name", name)
        .eq("student_id", student_id)
        .limit(1)
        .execute()
    )
    email = (resp.data[0].get("email") or "").strip() if resp.data else ""
    if not email:
        raise HTTPException(
            status_code=404,
            detail="이름과 학번이 일치하는 회원을 찾을 수 없습니다. 관리자에게 문의해주세요.",
        )
    return LoginLookupResponse(email=email)


@router.post("/change-password")
def change_password(payload: PasswordChangeRequest, user_id: str = Depends(require_auth)):
    """본인 비밀번호를 변경하고 최초 로그인 변경 요구 플래그를 해제합니다."""
    new_password = payload.new_password.strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 6자 이상이어야 합니다.")

    sb = get_supabase()
    profile = sb.table("users").select("student_id").eq("id", user_id).limit(1).execute()
    student_id = (profile.data[0].get("student_id") or "").strip() if profile.data else ""
    if student_id and new_password == student_id:
        raise HTTPException(status_code=400, detail="초기 비밀번호(학번)와 다른 비밀번호를 사용해주세요.")

    try:
        sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"비밀번호 변경에 실패했습니다: {exc}")

    sb.table("users").update({"must_change_password": False}).eq("id", user_id).execute()
    return {"ok": True}
