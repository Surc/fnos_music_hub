"""Validate actual audio and serve only the same immutable, owner-authorized file."""

import errno
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

from hub.errors import HubError


def fingerprint(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]


def open_private(root, filename):
    root, path = Path(root), Path(filename)
    if (
        not root.is_absolute()
        or not path.is_absolute()
        or ".." in path.parts
        or not path.is_relative_to(root)
        or path == root
    ):
        raise HubError("unsafe_file", "引擎文件不在用户授权目录内", 409)
    directory = fd = None
    try:
        # Each lookup is relative to an already-open directory. Checking a path
        # and then opening it by absolute name leaves its parents replaceable.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open("/", flags)
        for part in path.parts[1:-1]:
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size <= 0 or st.st_size > 2 * 1024**3:
            raise HubError("invalid_audio", "文件为空、过大或不是普通文件", 409)
        result, fd = fd, None
        return result, st
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise HubError(
                "unsafe_file", "不允许通过符号链接访问下载文件", 409
            ) from None
        raise HubError("file_unavailable", "下载文件不可用", 409) from None
    finally:
        if directory is not None:
            os.close(directory)
        if fd is not None:
            os.close(fd)


def validate_audio(root, filename, song, quality):
    fd, st = open_private(root, filename)
    try:
        media = f"/proc/self/fd/{fd}"
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                media,
            ],
            capture_output=True,
            timeout=30,
            pass_fds=(fd,),
            check=True,
        )
        data = json.loads(result.stdout)
        audio = next(s for s in data["streams"] if s.get("codec_type") == "audio")
        duration = float(data["format"]["duration"])
        expected = song["duration_seconds"]
        if expected <= 0 or abs(duration - expected) > max(3, expected * 0.03):
            raise ValueError("duration mismatch")
        codec = audio["codec_name"]
        if (quality in {"flac", "hires"} and codec != "flac") or (
            quality.endswith("mp3") and codec != "mp3"
        ):
            raise ValueError("codec mismatch")
        bitrate = int(audio.get("bit_rate") or data["format"].get("bit_rate") or 0)
        if quality.endswith("kmp3") and bitrate < int(quality.split("k")[0]) * 900:
            raise ValueError("bitrate mismatch")
        if quality == "hires" and (
            int(audio.get("sample_rate", 0)) < 48000
            or int(audio.get("bits_per_raw_sample", 0)) <= 16
        ):
            raise ValueError("not hires")
        # Probe alone is insufficient: decode the entire file to catch truncated audio.
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                media,
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=180,
            pass_fds=(fd,),
            check=True,
        )
        os.lseek(fd, 0, os.SEEK_SET)
        h = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            h.update(chunk)
        if fingerprint(os.fstat(fd)) != fingerprint(st):
            raise ValueError("file changed during verification")
        return {
            "bytes": st.st_size,
            "sha256": h.hexdigest(),
            "duration_seconds": duration,
            "codec": codec,
            "container": data["format"]["format_name"],
            "bitrate": bitrate,
            "fingerprint": fingerprint(st),
            "validation": "full_decode",
        }
    except (ValueError, KeyError, StopIteration, OSError, subprocess.SubprocessError):
        raise HubError(
            "invalid_audio", "音频解码、完整时长或实际音质校验未通过", 409
        ) from None
    finally:
        os.close(fd)


def open_asset(root, asset):
    fd, st = open_private(root, asset["file_path"])
    if fingerprint(st) != asset["fingerprint"]:
        os.close(fd)
        raise HubError("file_changed", "文件已变化，需要重新校验", 409)
    return fd
