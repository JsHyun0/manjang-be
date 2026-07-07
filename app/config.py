import os
from typing import List
import json

from dotenv import load_dotenv


load_dotenv()

from typing import List, Optional


def normalize_env_value(value: Optional[str]) -> Optional[str]:
    """Return value stripped of surrounding quotes and whitespace.

    Handles values like "'https://example.com'" or '"key"' by removing only
    a matching pair of quotes at both ends.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in ("'", '"'):
        return trimmed[1:-1].strip()
    return trimmed


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = normalize_env_value(os.getenv(name))
    if value is None or value == "":
        return default
    return value


SUPABASE_URL: Optional[str] = get_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = get_env("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET: Optional[str] = get_env("SUPABASE_JWT_SECRET")

# 회원 시트 동기화: 기본 구글 스프레드시트 URL (관리자 요청에서 덮어쓸 수 있음)
MEMBER_SHEET_URL: Optional[str] = get_env("MEMBER_SHEET_URL")
# 사전 등록 회원의 가상 이메일 도메인: {학번}@{도메인}
MEMBER_EMAIL_DOMAIN: str = get_env("MEMBER_EMAIL_DOMAIN", "member.manjang.site")


def get_allowed_origins() -> List[str]:
    raw = get_env("ALLOWED_ORIGINS")
    default_prod = [
        "https://www.manjang.site",
        "https://manjang.vercel.app",
        "https://manjang-vue.vercel.app",
    ]
    default_dev = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 1) 미설정: 안전한 기본값 반환
    if raw is None or not raw.strip():
        return default_prod + default_dev

    origins: List[str] = []

    # 2) JSON 배열로 설정된 경우: 파싱
    try:
        maybe = json.loads(raw)
        if isinstance(maybe, list):
            origins = [str(x).strip().strip("'\"") for x in maybe if str(x).strip()]
        else:
            raise ValueError("not a list")
    except Exception:
        # 3) CSV 또는 []가 포함된 CSV: 수동 파싱
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        tokens = [t.strip().strip("'\"") for t in s.split(",") if t.strip()]
        origins = tokens

    # 개발 도메인은 항상 포함
    origins += default_dev
    # 기본 프로덕션 도메인도 중복 없이 합치기 (환경변수에 실수로 빠진 경우 대비)
    origins = list(dict.fromkeys(origins + default_prod))

    return origins


def require_env(name: str) -> str:
    value = normalize_env_value(os.getenv(name))
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


