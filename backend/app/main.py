from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, me, mentor, navigator, programs, sop, timeline, visa
from app.config import get_settings
from app.ml.admit import load_model, model_info

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.frontend_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router)
app.include_router(catalog.router)
app.include_router(navigator.router)
app.include_router(mentor.router)
app.include_router(programs.router)
app.include_router(timeline.router)
app.include_router(sop.router)
app.include_router(visa.router)

load_model()  # load the admit model at startup rather than on the first request


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment, "admit_model": model_info()["version"]}
