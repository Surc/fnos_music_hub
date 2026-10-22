import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MANIFEST_ITEMS = 1000
MAX_MANIFEST_BYTES = 512 * 1024


def now():
    return datetime.now(UTC).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    instance_id: str
    user_guid: str

    @property
    def key(self):
        return canonical([self.instance_id, self.user_guid])


class TrackRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    provider: Literal["kuwo", "qq", "netease"]
    id_type: str = Field(min_length=1, max_length=32)
    id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def identity_type(self):
        allowed = {"kuwo": {"rid"}, "qq": {"songmid", "songid"}, "netease": {"songid"}}
        if self.id_type not in allowed[self.provider]:
            raise ValueError("provider/id_type mismatch")
        if self.id_type in {"rid", "songid"} and (
            not self.id.isascii() or not self.id.isdecimal() or int(self.id) <= 0
        ):
            raise ValueError("numeric ID must be a positive decimal string")
        if self.id_type == "songmid" and not self.id.isalnum():
            raise ValueError("invalid songmid")
        return self

    @property
    def key(self):
        return canonical(self.model_dump())


class ManifestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracks: list[TrackRef] = Field(min_length=1, max_length=MAX_MANIFEST_ITEMS)


class SubmitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    quality: Literal["128kmp3", "320kmp3", "flac", "hires"] = "320kmp3"
    target_ref: Literal["private"] = "private"


def make_manifest(owner: Principal, songs: list[dict]):
    # Each occurrence is independent: identical songs are not deduplicated.
    manifest = {
        "schema_version": 1,
        "snapshot_id": uuid4().hex,
        "owner": owner.model_dump(),
        "captured_at": now(),
        "source": {"kind": "explicit_selection", "adapter": "explicit-selection-v1"},
        "complete": True,
        "source_total": len(songs),
        "fetched_count": len(songs),
        "ordered_entries": [
            {"occurrence_id": uuid4().hex, "position": i, "song": song}
            for i, song in enumerate(songs)
        ],
    }
    if len(canonical(manifest).encode()) > MAX_MANIFEST_BYTES:
        from .errors import HubError

        raise HubError("capacity_exceeded", "清单超过 512 KiB，请减少条目", 413)
    manifest["content_hash"] = digest(manifest)
    return manifest
