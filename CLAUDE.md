# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
conda activate ai
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`

To run alongside the frontend, use `./dev-local.sh` from the monorepo root.

## Architecture

Single `app/` package — no sub-packages except `routers/`.

| File | Role |
|------|------|
| `main.py` | FastAPI app, CORS middleware, router registration |
| `config.py` | Env loading with `get_env()` (strips stray quotes); `get_allowed_origins()` accepts JSON array or CSV string; dev + prod origins always merged in |
| `db.py` | `get_supabase()` — TTL-cached singleton Supabase client (default 5 min, `SUPABASE_CLIENT_TTL_SECONDS`); also contains legacy helper functions (`create_user`, `create_debate`, etc.) that are not used by routers |
| `models.py` | Pydantic v2 models for all three domains |
| `routers/debates.py` | Debates CRUD + participants (`debate_participants` table) + winner setting |
| `routers/reservations.py` | Room reservations — overlap check helper, opponent-booking warning logic, `/month` bulk query endpoint |
| `routers/records.py` | Legacy debate records CRUD with Supabase `or_()` full-text search |

### Key design notes

- **supabase-py 2.x** does not support chaining `.select()` after `.update()` or `.delete()`, so routers that need the updated row do a separate re-fetch.
- Overlap detection in `reservations.py` (`_check_overlap`) is intentionally commented out — enforcement is relaxed for now.
- `ReservationCreateResponse` includes a `warn_opponent_booked` flag: set when the opposing debate team member has already booked overlapping time in the same debate.
- `records` router search uses Supabase `or_()` with `ilike` for text fields and `cs` (contains) for the `participantNames` array column.

## Environment variables

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
ALLOWED_ORIGINS          # JSON array or CSV; dev + prod origins always appended
SUPABASE_CLIENT_TTL_SECONDS=300  # optional
```

## Deployment

Docker → Google Cloud Run. The `Dockerfile` uses `python:3.11-slim` and exposes port 8080. Redeploy via `be_redeploy.sh` in the monorepo root.
