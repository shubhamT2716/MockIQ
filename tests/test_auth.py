import pytest
from fastapi.testclient import TestClient

from app.adapters.db import make_session_factory
from app.adapters.llm_fake import FakeLLM
from app.auth_service import AuthService
from app.config import TEST_ACCOUNT, Settings
from app.core.auth import LoginLimiter, TooManyAttempts, hash_password, verify_password
from app.main import create_app
from tests.conftest import signup


def test_password_hashing():
    h = hash_password("s3cret-pass")
    assert h.startswith("scrypt$") and "s3cret" not in h
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")
    assert hash_password("same") != hash_password("same")  # salted


def test_signup_login_logout(anon):
    assert anon.get("/api/auth/me").status_code == 401
    user = signup(anon, email="Mixed.Case@Example.com")
    assert user["email"] == "mixed.case@example.com"
    cookie = anon.cookies.get("mockiq_session")
    assert cookie and len(cookie) > 30
    assert anon.get("/api/auth/me").json()["name"] == "Asha"
    assert anon.post("/api/auth/logout").status_code == 204
    assert anon.get("/api/auth/me").status_code == 401
    r = anon.post("/api/auth/login", json={"email": "mixed.case@example.com", "password": "correct-horse-1"})
    assert r.status_code == 200 and anon.get("/api/auth/me").status_code == 200


def test_signup_validation(anon):
    bad = [({"name": "A", "email": "nope", "password": "longenough"}, "valid email"),
           ({"name": "A", "email": "a@b.co", "password": "short"}, "8 characters"),
           ({"name": " ", "email": "a@b.co", "password": "longenough"}, "name")]
    for body, msg in bad:
        r = anon.post("/api/auth/signup", json=body)
        assert r.status_code == 422 and msg in r.json()["detail"]
    signup(anon, email="dup@x.com")
    r = anon.post("/api/auth/signup", json={"name": "B", "email": "DUP@x.com", "password": "longenough"})
    assert r.status_code == 422 and "already exists" in r.json()["detail"]


def test_login_errors_do_not_reveal_accounts(anon):
    signup(anon, email="real@x.com")
    anon.post("/api/auth/logout")
    a = anon.post("/api/auth/login", json={"email": "real@x.com", "password": "wrong-password"})
    b = anon.post("/api/auth/login", json={"email": "ghost@x.com", "password": "wrong-password"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_rate_limit(anon):
    signup(anon, email="rl@x.com")
    anon.post("/api/auth/logout")
    for _ in range(5):
        anon.post("/api/auth/login", json={"email": "rl@x.com", "password": "nope-nope"})
    r = anon.post("/api/auth/login", json={"email": "rl@x.com", "password": "correct-horse-1"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_limiter_window_expires():
    t = [0.0]
    lim = LoginLimiter(max_failures=2, window_sec=60, clock=lambda: t[0])
    lim.fail("k"); lim.fail("k")
    with pytest.raises(TooManyAttempts):
        lim.check("k")
    t[0] = 61
    lim.check("k")


def test_memory_database_shares_accounts_across_sessions():
    factory = make_session_factory("sqlite:///:memory:")
    auth = AuthService(factory)
    user, token = auth.signup("Ada", "ada@example.com", "correct-horse-1")
    loaded = auth.user_for_token(token)
    assert loaded is not None and loaded.id == user.id and loaded.email == "ada@example.com"
    other = make_session_factory("sqlite:///:memory:")
    assert AuthService(other).user_for_token(token) is None


def test_seeded_test_account_can_sign_in():
    s = Settings(llm_provider="fake", database_url="sqlite:///:memory:", eval_passes=1, seed_test_user=True)
    app = create_app(s, llm=FakeLLM())
    with TestClient(app) as c:
        health = c.get("/api/health")
        assert health.status_code == 200
        assert health.json()["test_account"]["email"] == TEST_ACCOUNT["email"]
        r = c.post("/api/auth/login", json={"email": TEST_ACCOUNT["email"], "password": TEST_ACCOUNT["password"]})
        assert r.status_code == 200
        assert c.get("/api/auth/me").json()["name"] == TEST_ACCOUNT["name"]
        created = c.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "rounds": [0]})
        assert created.status_code == 200


def test_interview_routes_require_auth(anon):
    assert anon.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2"}).status_code == 401
    assert anon.get("/api/me/dashboard").status_code == 401
    assert anon.get("/api/role-packs").status_code == 200  # public catalog


def test_cross_site_post_blocked(client):
    r = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2"},
                    headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_users_cannot_see_each_others_data(client, other_client):
    prof = client.post("/api/profiles", data={"text": "Backend engineer with Java, Spring, Redis and Kafka experience. " * 3}).json()
    s = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "rounds": [0]}).json()
    sid = s["id"]
    for method, path in [("get", f"/api/sessions/{sid}"), ("post", f"/api/sessions/{sid}/start"),
                         ("post", f"/api/sessions/{sid}/end"), ("get", f"/api/sessions/{sid}/report")]:
        assert getattr(other_client, method)(path).status_code == 404, path
    r = other_client.post("/api/sessions", json={"profile_id": prof["id"], "role_pack": "backend-sde", "level": "L2"})
    assert r.status_code == 404  # can't use someone else's resume
    assert other_client.get("/api/me/dashboard").json()["stats"]["interviews"] == 0
    assert other_client.get("/api/me/profile").json() is None
    assert client.get("/api/me/profile").json()["id"] == prof["id"]
