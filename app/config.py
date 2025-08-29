import os
from typing import List

from dotenv import load_dotenv


load_dotenv()

from typing import List, Optional

SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_allowed_origins() -> List[str]:
    raw = os.getenv("ALLOWED_ORIGINS")
    if raw is None or not raw.strip():
        # 개발 기본값: Vite dev server
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    parsed = [origin.strip() for origin in raw.split(",") if origin.strip()]
    parsed.append("http://localhost:5173")
    # 잘못된 설정으로 비어있으면 안전 폴백
    return parsed or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


