import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm_fake import FakeLLM
from app.config import Settings
from app.core.models import utcnow
from app.core.planner import build_plan
from app.core.rolepacks import load_rolepacks
from app.main import create_app


@pytest.fixture(scope="session")
def packs():
    return load_rolepacks(Settings().rolepacks_dir)


@pytest.fixture
def state(packs):
    return build_plan(packs["backend-sde"], "L2", ["java-spring"], None, rng=random.Random(7))


@pytest.fixture
def app(tmp_path):
    s = Settings(llm_provider="fake", database_url=f"sqlite:///{tmp_path}/t.db", eval_passes=3,
                 seed_test_user=False)
    return create_app(s, llm=FakeLLM())


def signup(c, name="Asha", email="asha@example.com", password="correct-horse-1"):
    r = c.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def anon(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(app):
    """A signed-in user."""
    with TestClient(app) as c:
        signup(c)
        yield c


@pytest.fixture
def other_client(app):
    with TestClient(app) as c:
        signup(c, name="Ravi", email="ravi@example.com")
        yield c


@pytest.fixture
def later():
    return lambda minutes: utcnow() + timedelta(minutes=minutes)
