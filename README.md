## Manjang Backend (FastAPI + Supabase)

FastAPI 기반의 백엔드 서비스로, Supabase(PostgreSQL)와 연동되어 `manjang-vue` 프론트엔드에서 사용하는 토론 기록(Records)과 동아리방 예약(Reservations) API를 제공합니다.

### 사전 준비
- Python 3.10+
- Supabase 프로젝트 (URL, Service Role Key 필요)
- `.env` 파일 작성 (아래 참고)

### 환경 변수 (.env)
`.env.example`를 참고하여 프로젝트 루트(`manjang-be/`)에 `.env`를 생성하세요.

```
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
ALLOWED_ORIGINS=http://localhost:5173
```

### 설치 및 실행
Conda 환경을 사용하신다면 활성화 후 진행하세요.

```bash
conda activate ai
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

서버가 실행되면:
- API Docs: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

### 데이터베이스 스키마
Supabase의 SQL Editor에서 `sql/schema.sql` 내용을 실행하여 테이블을 생성하세요.

### API 개요
- Health: `GET /health`
- Records
  - `GET /records` (검색/필터/정렬 지원)
  - `POST /records`
  - `PUT /records/{id}`
  - `DELETE /records/{id}`
- Reservations
  - `GET /reservations` (옵션: `date=YYYY-MM-DD`)
  - `POST /reservations`
  - `DELETE /reservations/{id}`

### CORS
기본 허용 오리진은 `http://localhost:5173` 입니다. 필요 시 `.env`의 `ALLOWED_ORIGINS`를 수정하세요.


