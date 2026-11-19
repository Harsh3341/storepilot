"""Single-owner credentials and opaque, persistent browser sessions."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets


PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 7 * 24 * 60 * 60
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_FAILED_ATTEMPTS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_owner (
 id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_sessions (
 token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts (
 id TEXT PRIMARY KEY, ip TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS auth_attempts_ip_created ON auth_attempts(ip,created_at);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
"""


class AuthError(ValueError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _utf8(value: str) -> bytes | None:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        return None


def _username(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise AuthError("Owner username must contain between 1 and 128 characters.")
    value = value.strip()
    if _utf8(value) is None:
        raise AuthError("Owner username must contain valid Unicode text.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AuthError("Owner username cannot contain control characters.")
    return value


def _password(value: str):
    if not isinstance(value, str) or not 12 <= len(value) <= 1024:
        raise AuthError("Owner password must contain between 12 and 1024 characters.")
    if _utf8(value) is None:
        raise AuthError("Owner password must contain valid Unicode text.")


def hash_password(password: str) -> str:
    """Return a salted, portable hash suitable for trusted owner provisioning."""
    _password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _decode_hash(encoded_hash: str) -> tuple[bytes, bytes]:
    if not isinstance(encoded_hash, str):
        raise AuthError("Owner password hash has an invalid format.")
    pattern = rf"pbkdf2_sha256\${PASSWORD_ITERATIONS}\$([0-9a-fA-F]{{32}})\$([0-9a-fA-F]{{64}})"
    match = re.fullmatch(pattern, encoded_hash)
    if match is None:
        raise AuthError("Owner password hash must use PBKDF2-SHA256 with 600000 iterations, a 16-byte salt, and a 32-byte digest.")
    return bytes.fromhex(match[1]), bytes.fromhex(match[2])


def _matches(password: str, encoded_hash: str) -> bool:
    salt, expected = _decode_hash(encoded_hash)
    if not isinstance(password, str) or len(password) > 1024:
        return False
    encoded_password = _utf8(password)
    candidate = hashlib.pbkdf2_hmac("sha256", encoded_password or b"", salt, PASSWORD_ITERATIONS)
    return encoded_password is not None and hmac.compare_digest(candidate, expected)


def _token_hash(raw_token: str | None) -> str | None:
    if not isinstance(raw_token, str) or not raw_token or len(raw_token) > 256:
        return None
    encoded_token = _utf8(raw_token)
    return hashlib.sha256(encoded_token).hexdigest() if encoded_token is not None else None


class Auth:
    def __init__(self, database):
        self.database = database
        self.connection = database.connection
        with self.database.lock:
            self.connection.executescript(SCHEMA)

    def has_owner(self) -> bool:
        with self.database.lock:
            return self.connection.execute("SELECT id FROM auth_owner WHERE id=1").fetchone() is not None

    def setup_owner(self, username: str, password: str):
        """Provision/reset through a trusted command, revoking previous sessions."""
        username = _username(username)
        self.setup_owner_hash(username, hash_password(password))

    def setup_owner_hash(self, username: str, encoded_hash: str):
        """Provision trusted environment credentials; identical values are a no-op."""
        username = _username(username)
        _decode_hash(encoded_hash)
        with self.database.transaction():
            current = self.connection.execute("SELECT username,password_hash FROM auth_owner WHERE id=1").fetchone()
            if current and current["username"] == username and hmac.compare_digest(current["password_hash"], encoded_hash):
                return
            self.connection.execute("INSERT INTO auth_owner(id,username,password_hash) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,password_hash=excluded.password_hash", (username, encoded_hash))
            self.connection.execute("DELETE FROM auth_sessions")
            self.connection.execute("DELETE FROM auth_attempts")

    def login(self, username: str, password: str, client_ip: str) -> dict:
        now = _now()
        created_at = _timestamp(now)
        cutoff = _timestamp(now - ATTEMPT_WINDOW)
        ip = str(client_ip or "unknown")[:256]
        failure = None
        result = None
        with self.database.transaction():
            owner = self.connection.execute("SELECT username,password_hash FROM auth_owner WHERE id=1").fetchone()
            if owner is None:
                raise AuthError("The owner account has not been configured.", 409)
            self.connection.execute("DELETE FROM auth_attempts WHERE created_at<?", (cutoff,))
            self.connection.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (created_at,))
            attempts = self.connection.execute("SELECT COUNT(*) FROM auth_attempts WHERE ip=? AND created_at>=?", (ip, cutoff)).fetchone()[0]
            if attempts >= MAX_FAILED_ATTEMPTS:
                failure = AuthError("Too many failed login attempts. Try again in 15 minutes.", 429)
            else:
                # Derive the candidate even for a wrong username, avoiding a
                # quick username-only rejection. Failed attempts must commit.
                password_matches = _matches(password, owner["password_hash"])
                encoded_username = _utf8(username.strip()) if isinstance(username, str) else None
                username_matches = encoded_username is not None and hmac.compare_digest(encoded_username, owner["username"].encode("utf-8"))
                if not username_matches or not password_matches:
                    self.connection.execute("INSERT INTO auth_attempts(id,ip,created_at) VALUES(?,?,?)", (secrets.token_hex(16), ip, created_at))
                    failure = AuthError("Invalid username or password.", 401)
                else:
                    token = secrets.token_urlsafe(32)
                    csrf_token = secrets.token_urlsafe(32)
                    expires_at = _timestamp(now + timedelta(seconds=SESSION_SECONDS))
                    self.connection.execute("INSERT INTO auth_sessions(token_hash,csrf_token,created_at,expires_at) VALUES(?,?,?,?)", (_token_hash(token), csrf_token, created_at, expires_at))
                    result = {"token": token, "username": owner["username"], "csrf_token": csrf_token, "expires_at": expires_at}
        if failure:
            raise failure
        return result

    def session(self, raw_token: str | None) -> dict | None:
        token_hash = _token_hash(raw_token)
        if token_hash is None:
            return None
        with self.database.lock:
            row = self.connection.execute("SELECT o.username,s.csrf_token,s.expires_at FROM auth_sessions s CROSS JOIN auth_owner o WHERE s.token_hash=? AND o.id=1 AND s.expires_at>?", (token_hash, _timestamp(_now()))).fetchone()
            if row is None:
                return None
            return {"username": row["username"], "csrf_token": row["csrf_token"], "expires_at": row["expires_at"]}

    def logout(self, raw_token: str | None):
        token_hash = _token_hash(raw_token)
        if token_hash is not None:
            with self.database.transaction():
                self.connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
