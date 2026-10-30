import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters.db import make_session_factory
from .api.routes import router
from .auth_service import AuthService
from .config import TEST_ACCOUNT, Settings, settings as default_settings
from .core.auth import AuthError
from .core.rolepacks import load_rolepacks
from .services import InterviewService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _seed_test_user(auth: AuthService) -> None:
    log = logging.getLogger("mockiq")
    try:
        auth.signup(TEST_ACCOUNT["name"], TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])
    except AuthError:
        log.info("Test account already present: %s", TEST_ACCOUNT["email"])
        return
    log.info("Test account ready (in this process only): %s / %s", TEST_ACCOUNT["email"], TEST_ACCOUNT["password"])


def build_llm(s: Settings):
    if s.llm_provider == "fake":
        from .adapters.llm_fake import FakeLLM
        return FakeLLM()
    from .adapters.llm_anthropic import AnthropicLLM
    if not s.anthropic_api_key:
        logging.getLogger("mockiq").warning("ANTHROPIC_API_KEY is not set; interview calls will fail until it is.")
    return AnthropicLLM(s)


def create_app(s: Settings | None = None, llm=None) -> FastAPI:
    s = s or default_settings
    app = FastAPI(title="MockIQ", version="0.2.0")
    packs = load_rolepacks(s.rolepacks_dir)
    session_factory = make_session_factory(s.database_url)
    app.state.service = InterviewService(llm or build_llm(s), packs, session_factory, s)
    app.state.auth = AuthService(session_factory)
    if s.seed_test_user:
        _seed_test_user(app.state.auth)

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        """Cookie auth needs CSRF protection: reject state-changing requests from other sites."""
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if origin and urlparse(origin).netloc != host:
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
            if not origin and request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app


# Run with: uvicorn app.main:create_app --factory --reload
