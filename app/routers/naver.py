import os

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from urllib.parse import quote
from dotenv import load_dotenv
import httpx

from app.db import get_supabase, get_user_by_email, create_user
from app.models import DebateRecord, DebateRecordCreate

router = APIRouter()
load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
redirect_URI = 'http://localhost:8000/naver/callback'

def get_naver_auth_url(state: str='state'):
    return (
        'https://nid.naver.com/oauth2.0/authorize?response_type=code&client_id=' + NAVER_CLIENT_ID + '&redirect_uri=' + redirect_URI + '&state=' + state
    )

# 네이버 토큰 요청
async def get_naver_token(code: str):
    token_url = "https://nid.naver.com/oauth2.0/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    params = {
        "grant_type": "authorization_code",
        "client_id": NAVER_CLIENT_ID,
        "client_secret": NAVER_CLIENT_SECRET,
        "code": code,
        "state": "state"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, headers=headers, data=params)
        response.raise_for_status()
        return response.json()

# 네이버 사용자 정보 요청
async def get_naver_user_info(access_token: str):
    user_info_url = "https://openapi.naver.com/v1/nid/me"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(user_info_url, headers=headers)
        response.raise_for_status()
        return response.json()

@router.get("/")
def naver_auth(request: Request):
    return RedirectResponse(get_naver_auth_url())

@router.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if state != "state":
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # 네이버에서 발급된 액세스 토큰을 요청
    token_response = await get_naver_token(code)
    access_token = token_response.get("access_token")
    
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to get access token")

    # 액세스 토큰을 사용하여 사용자 정보를 요청
    user_info = await get_naver_user_info(access_token)

    # 네이버 응답 파싱
    profile = user_info.get("response", {}) if isinstance(user_info, dict) else {}
    naver_id = profile.get("id")
    email = profile.get("email")
    name = profile.get("name") or profile.get("nickname") or "사용자"

    # 이메일이 동의 범위에 없을 수 있으므로 대체 이메일 생성 (스키마상 not null, unique)
    if not email:
        if not naver_id:
            raise HTTPException(status_code=400, detail="Failed to parse Naver user profile")
        email = f"naver_{naver_id}@naver.local"

    # 이미 가입된 경우에는 곧바로 홈으로
    existing = get_user_by_email(email)
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
    if existing is not None and (existing.get("sid") is not None):
        redirect_url = f"{frontend_base}/home?login=success&name={quote(existing.get('name') or name)}&email={quote(email)}"
        return RedirectResponse(url=redirect_url)

    # 최초 로그인(회원가입 미완): sID 입력 페이지로 리다이렉트
    redirect_url = f"{frontend_base}/login?onboarding=1&name={quote(name)}&email={quote(email)}"
    return RedirectResponse(url=redirect_url)


@router.post("/complete")
async def complete_registration(request: Request):
    body = await request.json()
    email = body.get("email")
    name = body.get("name")
    sid = body.get("sid")

    if not email or not sid:
        raise HTTPException(status_code=400, detail="email and sid are required")

    # 이미 존재하면 sid 유효성 확인 후 업데이트 금지(정책상 가입 후 sid 변경 불가)
    existing = get_user_by_email(email)
    if existing is not None:
        if existing.get("sid"):
            # 이미 가입 완료된 사용자
            frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
            redirect_url = f"{frontend_base}/home?login=success&name={quote(existing.get('name') or name or '')}&email={quote(email)}"
            return JSONResponse({"status": "ok", "redirect": redirect_url})
        else:
            # sid만 업데이트 허용
            client = get_supabase()
            updated = (
                client.table("users")
                .update({"sid": sid, "name": name or existing.get("name")})
                .eq("email", email)
                .select("*")
                .limit(1)
                .execute()
            )
            row = updated.data[0] if updated.data else existing
            frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
            redirect_url = f"{frontend_base}/home?login=success&name={quote(row.get('name') or '')}&email={quote(email)}"
            return JSONResponse({"status": "ok", "redirect": redirect_url})

    # 미존재: 새로 생성
    created = create_user(email=email, name=name, sid=sid)
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
    redirect_url = f"{frontend_base}/home?login=success&name={quote(created.get('name') or name or '')}&email={quote(email)}"
    return JSONResponse({"status": "ok", "redirect": redirect_url})
