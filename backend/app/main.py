from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, content, growth, loan, loan_application, me, mentor, navigator, programs, sop, timeline, visa
from app import scheduler, storage
from app.config import get_settings
from app.ml import lead
from app.ml.admit import load_model, model_info

settings = get_settings()



@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

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
app.include_router(loan_application.router)
app.include_router(loan.router)
app.include_router(growth.router)
app.include_router(content.router)

load_model()  # load the ML models at startup rather than on the first request
lead.load_model()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment, "admit_model": model_info()["version"], "lead_model": lead.model_info()["version"],
            "storage": storage.configured()}
