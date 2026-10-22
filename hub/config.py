import json
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    engine_url: str
    engine_token_env: str = Field(min_length=1)
    download_root: Path

    @field_validator("download_root")
    @classmethod
    def absolute_root(cls, value):
        if not value.is_absolute() or value == Path("/"):
            raise ValueError("download_root must be an absolute private directory")
        return value.resolve()

    @field_validator("engine_url")
    @classmethod
    def local_engine(cls, value):
        url = urlsplit(value)
        if url.scheme != "http" or url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Hot must be on this NAS loopback interface")
        if (
            url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("engine_url must contain only origin")
        return value.rstrip("/")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instance_id: str = Field(min_length=1, max_length=128)
    data_dir: Path
    bridge_url: str
    bridge_key_env: str = "HUB_BRIDGE_KEY"
    public_origin: str
    secure_cookie: bool = True
    admin_guids: frozenset[str] = frozenset()
    users: dict[str, EngineConfig] = Field(default_factory=dict)
    session_seconds: int = Field(default=43200, ge=60, le=604800)
    poll_seconds: float = Field(default=3, ge=0.2, le=60)
    qq_accounts_enabled: bool = False

    @field_validator("bridge_url", "public_origin")
    @classmethod
    def trusted_url(cls, value):
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("a fixed http(s) URL without credentials is required")
        return value.rstrip("/")

    @model_validator(mode="after")
    def private_engines(self):
        origins, roots = set(), []
        for engine in self.users.values():
            url = urlsplit(engine.engine_url)
            # localhost, IPv4 and IPv6 loopback cannot alias the same port.
            key = url.port or 80
            if key in origins:
                raise ValueError("each user needs a distinct Hot runtime/port")
            origins.add(key)
            root = engine.download_root
            if any(
                root.is_relative_to(other) or other.is_relative_to(root)
                for other in roots
            ):
                raise ValueError("user download directories must not overlap")
            roots.append(root)
        if urlsplit(self.public_origin).path not in ("", "/"):
            raise ValueError("public_origin must be an origin")
        if self.secure_cookie and not self.public_origin.startswith("https://"):
            raise ValueError("secure cookies require HTTPS public_origin")
        return self

    @classmethod
    def load(cls, path: str):
        file = Path(path).resolve()
        data = json.loads(file.read_text())
        data["data_dir"] = (file.parent / data["data_dir"]).resolve()
        return cls.model_validate(data)
