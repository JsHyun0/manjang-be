from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_allowed_origins
from app.routers.records import router as records_router
from app.routers.reservations import router as reservations_router
from app.routers.debates import router as debates_router
from app.routers.members import router as members_router
from app.routers.account import router as account_router
from app.routers.tournaments import router as tournaments_router

from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Manjang Backend", version="0.1.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


app.include_router(records_router, prefix="/records", tags=["records"])
app.include_router(reservations_router, prefix="/reservations", tags=["reservations"])
app.include_router(debates_router, prefix="/debates", tags=["debates"])
app.include_router(members_router, prefix="/members", tags=["members"])
app.include_router(account_router, prefix="/auth", tags=["auth"])
app.include_router(tournaments_router, prefix="/tournaments", tags=["tournaments"])
