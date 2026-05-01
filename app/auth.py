from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException

from app.config import SUPABASE_JWT_SECRET
from app.db import get_supabase

_ALGORITHM = "HS256"
_AUDIENCE = "authenticated"


def _decode_token(token: str) -> dict:
    secret = SUPABASE_JWT_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="서버 인증 설정이 누락되었습니다.")
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM], audience=_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


def require_auth(authorization: Optional[str] = Header(default=None)) -> str:
    """Supabase JWT를 검증하고 user_id(sub)를 반환합니다."""
    if not authorization:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization 헤더는 'Bearer <token>' 형식이어야 합니다.")
    payload = _decode_token(authorization.removeprefix("Bearer "))
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="토큰에 사용자 식별자가 없습니다.")
    return user_id


def require_admin(user_id: str = Depends(require_auth)) -> str:
    """DB의 public.users.role을 직접 조회하여 admin 여부를 확인합니다.
    user_metadata는 사용하지 않으므로 클라이언트 위변조에 안전합니다.
    """
    sb = get_supabase()
    result = sb.table("users").select("role").eq("id", user_id).limit(1).execute()
    if not result.data or result.data[0].get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user_id


def is_admin_user(user_id: str) -> bool:
    """소유자 확인과 병행하여 admin 여부를 인라인으로 확인할 때 쓰는 헬퍼."""
    sb = get_supabase()
    result = sb.table("users").select("role").eq("id", user_id).limit(1).execute()
    return bool(result.data and result.data[0].get("role") == "admin")
