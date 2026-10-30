"""Password hashing, tokens and login throttling. Standard library only."""
import base64
import hashlib
import hmac
import re
import secrets
import threading
import time

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=64)


class AuthError(Exception):
    """Wrong credentials, or invalid signup input. Message is safe to show the user."""


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"Too many sign-in attempts. Try again in {max(1, retry_after // 60)} minutes.")
        self.retry_after = retry_after


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError("Enter a valid email address.")
    return email


def check_password_rules(password: str) -> None:
    if len(password or "") < 8:
        raise AuthError("Use at least 8 characters for your password.")
    if len(password) > 200:
        raise AuthError("Password is too long.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


# Used to make "unknown email" take as long as "wrong password" (no account enumeration by timing).
DUMMY_HASH = hash_password(secrets.token_hex(8))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLimiter:
    """In-memory sliding window per key (email and IP). Swap for Redis with multiple servers."""

    def __init__(self, max_failures: int = 5, window_sec: int = 900, clock=time.monotonic):
        self.max, self.window, self.clock = max_failures, window_sec, clock
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, *keys: str) -> None:
        now = self.clock()
        with self._lock:
            for k in keys:
                recent = [t for t in self._fails.get(k, []) if now - t < self.window]
                self._fails[k] = recent
                if len(recent) >= self.max:
                    raise TooManyAttempts(int(self.window - (now - recent[0])))

    def fail(self, *keys: str) -> None:
        now = self.clock()
        with self._lock:
            for k in keys:
                self._fails.setdefault(k, []).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)
