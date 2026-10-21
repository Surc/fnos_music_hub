"""Reconcile persisted intents with Hot; never run a second download scheduler."""

import asyncio

from modules.download.assets import validate_audio

from .domain import Principal
from .errors import HubError

ACTIVE = {"waiting", "downloading", "processing", "paused", "interrupted"}


def engine_failure(job):
    message = str(job.get("errorMsg", "")).lower()
    if "not available in your region or country" in message:
        return {
            "code": "region_restricted",
            "message": "酷我拒绝了当前运行环境的地区访问；歌曲与收藏仍然保留",
        }
    if "bitrate 不匹配" in message or "format 不匹配" in message:
        return {
            "code": "quality_unavailable",
            "message": "平台未提供所选原生音质，没有自动降级",
        }
    return {
        "code": "download_failed",
        "message": "Hot 下载失败，请检查平台权限、音质与引擎日志",
    }


def matches(job, entry, quality):
    song = entry["song"]["engine_song"]
    return (
        job.get("platform") == song["platform"]
        and str(job.get("songId")) == str(song["id"])
        and job.get("songMid", "") == song["mid"]
        and job.get("quality") == quality
    )


class Reconciler:
    def __init__(self, store, engines):
        self.store, self.engines = store, engines
        self.lock = asyncio.Lock()

    async def tick(self):
        async with self.lock:
            for task in self.store.pending():
                try:
                    await self.reconcile(task)
                except HubError as exc:
                    task["last_error"] = {"code": exc.code, "message": exc.message}
                    self.store.save_task(task)

    async def reconcile(self, task):
        owner = Principal.model_validate(task["owner"])
        if task["runtime_key"] != self.engines.runtime_key(owner):
            task["status"] = "attention"
            task["last_error"] = {
                "code": "runtime_changed",
                "message": "用户引擎或授权目录已变化，请核对原任务",
            }
            self.store.save_task(task)
            return
        await self.engines.check_target(owner)
        jobs = await self.engines.tasks(owner)
        for entry in task["entries"]:
            if entry["status"] in {"completed", "failed"}:
                continue
            if entry["status"] == "queued":
                existing = [
                    j
                    for j in jobs
                    if j.get("status") in ACTIVE and matches(j, entry, task["quality"])
                ]
                if len(existing) == 1:
                    entry["engine_id"] = existing[0]["id"]
                    entry["status"] = "running"
                else:
                    # Persist intent before POST. A crash here is conservatively unknown.
                    entry["status"] = "submitting"
                    entry["before_ids"] = [j["id"] for j in jobs]
                    self.store.save_task(task)
                    try:
                        result = await self.engines.call(
                            owner,
                            "POST",
                            "/api/tasks",
                            {
                                "song": entry["song"]["engine_song"],
                                "desiredQuality": task["quality"],
                                "duplicateAction": "rename",
                            },
                        )
                        job = result.get("task") if isinstance(result, dict) else None
                        if (
                            not isinstance(job, dict)
                            or result.get("outcome") not in {"created", "existing"}
                            or not isinstance(job.get("id"), str)
                            or not matches(job, entry, task["quality"])
                        ):
                            raise HubError(
                                "outcome_unknown", "引擎接单结果未知，请核对任务", 409
                            )
                        entry["engine_id"], entry["status"] = job["id"], "running"
                        jobs = [j for j in jobs if j["id"] != job["id"]] + [job]
                    except HubError:
                        entry["status"] = "outcome_unknown"
                        entry["error"] = {
                            "code": "outcome_unknown",
                            "message": "接单结果未知，系统不会盲目重复下单",
                        }
                    self.store.save_task(task)
            if entry["status"] in {"submitting", "outcome_unknown"}:
                candidates = [
                    j
                    for j in jobs
                    if j["id"] not in entry.get("before_ids", [])
                    and matches(j, entry, task["quality"])
                ]
                if len(candidates) == 1:
                    entry["engine_id"], entry["status"], entry["error"] = (
                        candidates[0]["id"],
                        "running",
                        None,
                    )
                else:
                    entry["status"] = "outcome_unknown"
                    continue
            job = next((j for j in jobs if j["id"] == entry["engine_id"]), None)
            if job is None or not matches(job, entry, task["quality"]):
                entry["status"] = "outcome_unknown"
                entry["error"] = {
                    "code": "engine_task_missing",
                    "message": "原引擎任务不可确认，不自动重新创建",
                }
            elif job.get("status") == "completed":
                try:
                    info = await asyncio.to_thread(
                        validate_audio,
                        self.engines.config(owner).download_root,
                        job.get("filePath", ""),
                        entry["song"],
                        task["quality"],
                    )
                    # Deterministic asset ID makes a crash between these writes harmless.
                    asset_id = task["id"] + "-" + entry["occurrence_id"]
                    asset = {
                        "id": asset_id,
                        "track": entry["song"]["track"],
                        "title": entry["song"]["title"],
                        "artist": entry["song"]["artist"],
                        "quality": job["quality"],
                        "file_path": job["filePath"],
                        "runtime_key": task["runtime_key"],
                        "index_status": "unsupported",
                        **info,
                    }
                    self.store.save_asset(owner.key, asset)
                    entry["status"], entry["asset_id"] = "completed", asset_id
                except HubError as exc:
                    entry["status"], entry["error"] = (
                        "failed",
                        {"code": exc.code, "message": exc.message},
                    )
            elif job.get("status") == "error":
                entry["status"], entry["error"] = "failed", engine_failure(job)
            elif job.get("status") in {"paused", "interrupted"}:
                entry["status"] = "paused"
            else:
                entry["status"] = "running"
            entry["downloaded_bytes"] = job.get("downloaded", 0) if job else 0
            self.store.save_task(task)
        states = {e["status"] for e in task["entries"]}
        task["status"] = (
            "completed"
            if states == {"completed"}
            else "failed"
            if states <= {"completed", "failed"}
            else "attention"
            if "outcome_unknown" in states
            else "paused"
            if states <= {"paused", "completed", "failed"}
            else "running"
        )
        task.pop("last_error", None)
        self.store.save_task(task)
