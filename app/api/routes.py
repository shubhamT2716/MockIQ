from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from ..adapters.resume import UnsupportedFile
from ..auth_service import SESSION_DAYS, AuthService, User
from ..config import TEST_ACCOUNT
from ..core.auth import AuthError, TooManyAttempts
from ..core.interview_engine import SessionNotLive
from ..core.ports import LLMError
from ..core.state_machine import InvalidTransition
from ..services import InterviewService, NotFound

router = APIRouter(prefix="/api")
COOKIE = "mockiq_session"


def svc(request: Request) -> InterviewService:
    return request.app.state.service


def auth(request: Request) -> AuthService:
    return request.app.state.auth


def current_user(request: Request) -> User:
    user = auth(request).user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound as e:
        raise HTTPException(404, str(e))
    except (SessionNotLive, InvalidTransition) as e:
        raise HTTPException(409, str(e))
    except (UnsupportedFile, ValueError) as e:
        raise HTTPException(422, str(e))
    except LLMError as e:
        raise HTTPException(502, f"The AI interviewer could not respond: {e}")


# ---------------- auth ----------------
class SignupIn(BaseModel):
    name: str = Field(max_length=100)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=svc(request).settings.cookie_secure, path="/")


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


@router.post("/auth/signup")
def signup(request: Request, response: Response, body: SignupIn):
    try:
        user, token = auth(request).signup(body.name, body.email, body.password)
    except AuthError as e:
        raise HTTPException(422, str(e))
    _set_cookie(request, response, token)
    return _user_out(user)


@router.post("/auth/login")
def login(request: Request, response: Response, body: LoginIn):
    ip = request.client.host if request.client else "unknown"
    try:
        user, token = auth(request).login(body.email, body.password, ip)
    except TooManyAttempts as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.retry_after)})
    except AuthError as e:
        raise HTTPException(401, str(e))
    _set_cookie(request, response, token)
    return _user_out(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    auth(request).logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return _user_out(user)


# ---------------- catalog ----------------
@router.get("/role-packs")
def role_packs(request: Request):
    return svc(request).role_packs()


@router.get("/health")
def health(request: Request):
    s = svc(request)
    body = {"ok": True, "llm_provider": s.settings.llm_provider,
            "llm_configured": s.settings.llm_provider == "fake" or bool(s.settings.anthropic_api_key)}
    if s.settings.seed_test_user:
        body["test_account"] = {"email": TEST_ACCOUNT["email"], "password": TEST_ACCOUNT["password"]}
    return body


# ---------------- me ----------------
@router.get("/me/dashboard")
def dashboard(request: Request, tz_offset: int = 0, role_pack: str | None = None,
              user: User = Depends(current_user)):
    return svc(request).dashboard(user.id, max(-840, min(840, tz_offset)), role_pack)


@router.get("/me/profile")
def latest_profile(request: Request, user: User = Depends(current_user)):
    return svc(request).latest_profile(user.id)


@router.get("/me/weak-topics")
def weak_topics(request: Request, role_pack: str | None = None, user: User = Depends(current_user)):
    return svc(request).weak_topics(user.id, role_pack)


# ---------------- interviews ----------------
class CreateSession(BaseModel):
    profile_id: str | None = None
    role_pack: str
    level: str
    stack: list[str] = Field(default_factory=list)
    rounds: list[int] | None = None
    mode: Literal["voice", "chat"] = "voice"
    focus_weak: bool = False


class TurnIn(BaseModel):
    text: str = Field(default="", max_length=8000)
    code: str | None = Field(default=None, max_length=20000)
    command: Literal["skip"] | None = None


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


@router.post("/profiles")
async def create_profile(request: Request, text: str | None = Form(None), file: UploadFile | None = File(None),
                         user: User = Depends(current_user)):
    data = await file.read() if file else None
    if data and len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 5 MB. Upload a smaller resume.")
    return _run(svc(request).create_profile, user.id, text, file.filename if file else None, data)


@router.post("/sessions")
def create_session(request: Request, body: CreateSession, user: User = Depends(current_user)):
    return _run(svc(request).create_session, user.id, profile_id=body.profile_id, role_pack=body.role_pack,
                level=body.level, stack=body.stack, round_indexes=body.rounds, mode=body.mode,
                focus_weak=body.focus_weak)


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str, user: User = Depends(current_user)):
    return _run(svc(request).get_session, user.id, session_id)


@router.post("/sessions/{session_id}/start")
def start(request: Request, session_id: str, user: User = Depends(current_user)):
    return _run(svc(request).start, user.id, session_id)


@router.post("/sessions/{session_id}/turns")
def turn(request: Request, session_id: str, body: TurnIn, background: BackgroundTasks,
         user: User = Depends(current_user)):
    s = svc(request)
    view, completed = _run(s.turn, user.id, session_id, body.text, body.code, body.command)
    if completed:
        background.add_task(s.evaluate_session, session_id)
    return view


@router.post("/sessions/{session_id}/end")
def end(request: Request, session_id: str, background: BackgroundTasks, user: User = Depends(current_user)):
    s = svc(request)
    view = _run(s.end, user.id, session_id)
    background.add_task(s.evaluate_session, session_id)
    return view


@router.get("/sessions/{session_id}/report")
def report(request: Request, session_id: str, user: User = Depends(current_user)):
    return _run(svc(request).get_report, user.id, session_id)


@router.post("/sessions/{session_id}/report/rating", status_code=204)
def rate(request: Request, session_id: str, body: RatingIn, user: User = Depends(current_user)):
    _run(svc(request).rate_report, user.id, session_id, body.rating)
