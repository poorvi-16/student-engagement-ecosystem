from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import me
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
