import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Fixed local account. Created only when SEED_TEST_USER=true. Not a production login.
TEST_ACCOUNT = {
    "name": "Test User",
    "email": "tester@mockiq.local",
    "password": "test-pass-1",
}


class Settings(BaseModel):
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")  # anthropic | fake
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    interviewer_model: str = os.getenv("INTERVIEWER_MODEL", "claude-haiku-5-5")
    evaluator_model: str = os.getenv("EVALUATOR_MODEL", "claude-sonnet-5-5")
    eval_passes: int = int(os.getenv("EVAL_PASSES", "3"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./mockiq.db")
    # When true, create TEST_ACCOUNT at startup so local testing can sign in
    # without registering. Pair with sqlite:///:memory: so nothing is written to disk.
    seed_test_user: bool = os.getenv("SEED_TEST_USER", "false").lower() == "true"
    rolepacks_dir: str = os.getenv(
        "ROLEPACKS_DIR", os.path.join(os.path.dirname(__file__), "rolepacks")
    )
    max_resume_chars: int = 15000
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"  # true behind HTTPS


settings = Settings()
