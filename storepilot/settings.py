"""Validated runtime configuration for local and hosted StorePilot."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    environment: str = 'development'
    origin: str = ''
    database_url: str = ''
    owner_username: str = ''
    owner_password_hash: str = ''
    session_cookie: str = 'storepilot_session'
    groq_api_key: str = field(default='', repr=False)
    ai_model: str = 'openai/gpt-oss-120b'

    def __post_init__(self):
        if self.environment not in ('development', 'production'):
            raise ValueError('STOREPILOT_ENV must be development or production.')
        if bool(self.owner_username) != bool(self.owner_password_hash):
            raise ValueError('Set both owner username and password hash, or neither.')
        if self.origin:
            parsed = urlsplit(self.origin)
            try:
                parsed.port
            except ValueError as error:
                raise ValueError('STOREPILOT_ORIGIN contains an invalid port.') from error
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path not in ('', '/')
                    or parsed.query or parsed.fragment):
                raise ValueError('STOREPILOT_ORIGIN must be an HTTP(S) origin without a path.')
            object.__setattr__(self, 'origin', self.origin.rstrip('/'))
        if self.environment == 'production' and not self.origin.startswith('https://'):
            raise ValueError('Production requires an HTTPS STOREPILOT_ORIGIN.')
        if self.database_url and not self.database_url.startswith(('postgres://', 'postgresql://')):
            raise ValueError('STOREPILOT_DATABASE_URL must be a PostgreSQL connection URL.')

    @property
    def secure_cookies(self) -> bool:
        return self.environment == 'production'

    @property
    def trusted_hosts(self) -> list[str]:
        if self.environment == 'production':
            return [urlsplit(self.origin).hostname, '127.0.0.1', 'localhost']
        return list(dict.fromkeys(['127.0.0.1', 'localhost', 'testserver',
                                  *([urlsplit(self.origin).hostname] if self.origin else [])]))

    def accepts_origin(self, request) -> bool:
        origin = request.headers.get('origin')
        if origin is None:
            return True  # Non-browser clients still need credentials and CSRF for writes.
        expected = self.origin or str(request.base_url).rstrip('/')
        return origin == expected

    @classmethod
    def from_environment(cls, load_file=False):
        if load_file:
            load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
        on_render = os.environ.get('RENDER') == 'true'
        settings = cls(
            environment=os.environ.get('STOREPILOT_ENV', 'production' if on_render else 'development'),
            origin=os.environ.get('STOREPILOT_ORIGIN', os.environ.get('RENDER_EXTERNAL_URL', '')),
            database_url=os.environ.get('STOREPILOT_DATABASE_URL', ''),
            owner_username=os.environ.get('STOREPILOT_OWNER_USERNAME', ''),
            owner_password_hash=os.environ.get('STOREPILOT_OWNER_PASSWORD_HASH', ''),
            groq_api_key=os.environ.get('GROQ_API_KEY', '').strip(),
            ai_model=os.environ.get('STOREPILOT_AI_MODEL', 'openai/gpt-oss-120b'),
        )
        if on_render and settings.environment != 'production':
            raise ValueError('Render must use production mode.')
        if on_render and not settings.database_url:
            raise ValueError('Render requires STOREPILOT_DATABASE_URL; local files are temporary.')
        return settings
