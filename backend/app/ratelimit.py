"""In-memory rate limiting (sliding window). Fine for the single-instance deploy; move to Redis if the API is ever scaled out.

Three limits protect the shared free LLM quota and the database from one noisy client:
- AI endpoints (mentor, SOP, visa, timeline, navigator, uploads): per signed-in user (or IP)
- public endpoints (guides, share cards): per IP
- everything else: a generous per-identity and per-IP ceiling
"""

import hashlib
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

AI_PREFIXES = ("/mentor/chat", "/sop/review", "/visa", "/timeline/generate", "/navigator/run", "/loan/applications",
               "/admin/orchestrator", "/admin/simulate")  # only non-GET requests count as AI (polling the loan tracker is a GET)
PUBLIC_PREFIXES = ("/content", "/public")
LIMITS = {"ai": 20, "public": 60, "default": 240}  # requests per window, per identity
IP_CEILING = 600
WINDOW = 60.0


class SlidingWindow:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, now: float | None = None) -> float:
        """0.0 if the request is allowed (and counted), else the seconds until it would be."""
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and q[0] <= now - WINDOW:
            q.popleft()
        if len(q) >= limit:
            return max(1.0, q[0] + WINDOW - now)
        q.append(now)
        return 0.0

    def prune(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for k in [k for k, q in self.hits.items() if not q or q[-1] <= now - WINDOW]:
            del self.hits[k]


def classify(path: str, method: str, authed: bool) -> str:
    if method != "GET" and path.startswith(AI_PREFIXES):
        return "ai"
    if path.startswith(PUBLIC_PREFIXES) and not authed:
        return "public"
    return "default"


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, window: SlidingWindow | None = None) -> None:
        super().__init__(app)
        self.window = window or SlidingWindow()
        self.calls = 0

    async def dispatch(self, request: Request, call_next):
        if not get_settings().rate_limit_enabled or request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        ident = "u:" + hashlib.sha1(auth.encode()).hexdigest()[:16] if auth.lower().startswith("bearer ") else "ip:" + client_ip(request)
        kind = classify(request.url.path, request.method, auth.lower().startswith("bearer "))
        wait = max(self.window.check(f"{kind}:{ident}", LIMITS[kind]), self.window.check(f"ip:{client_ip(request)}", IP_CEILING))
        self.calls += 1
        if self.calls % 500 == 0:
            self.window.prune()
        if wait:
            return JSONResponse({"detail": "You're going a bit fast. Please wait a moment and try again."}, status_code=429,
                                headers={"Retry-After": str(int(wait) + 1)})
        return await call_next(request)
