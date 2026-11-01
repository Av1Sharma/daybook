"""Owned, checkpointed background Gmail imports. Cancellation preserves every commit."""

import asyncio
import json
import os
from fastapi import HTTPException
from .connectors import gmail_sync, canvas_sync, GMAIL_QUERY


class SyncJobs:
    def __init__(self, store, lock):
        self.store = store
        self.lock = lock
        self.task = None

    def running(self):
        return self.task is not None and not self.task.done()

    def start(self):
        if self.running() or self.lock.locked():
            return {"status": "running"}
        if not (
            os.getenv("GOOGLE_ACCOUNTS")
            or os.getenv("GOOGLE_REFRESH_TOKEN")
            or os.getenv("GMAIL_ACCESS_TOKEN")
            or os.getenv("CANVAS_TOKEN")
        ):
            raise HTTPException(422, "Connect a source before starting an import")
        self.task = asyncio.create_task(self.run())
        return {"status": "running"}

    async def run(self):
        async with self.lock:
            try:
                if os.getenv("CANVAS_TOKEN"):
                    try:
                        counts = self.store.ingest(await canvas_sync())
                        self.store.sync_status("canvas", "ok", json.dumps(counts))
                    except Exception:
                        self.store.sync_status(
                            "canvas",
                            "error",
                            "Canvas import paused. Check approved access; existing tasks were preserved.",
                        )
                if not (
                    os.getenv("GOOGLE_ACCOUNTS")
                    or os.getenv("GOOGLE_REFRESH_TOKEN")
                    or os.getenv("GMAIL_ACCESS_TOKEN")
                ):
                    return
                while True:
                    self.store.sync_status(
                        "gmail",
                        "running",
                        "Scanning the last 30 days. Progress is saved after each message.",
                    )
                    result = await gmail_sync(store=self.store)
                    if isinstance(result, list):  # Legacy single-account configuration.
                        result = self.store.ingest(result)
                    if not result.get("partial"):
                        self.store.sync_status(
                            "gmail",
                            "ok",
                            json.dumps(
                                {
                                    k: v
                                    for k, v in result.items()
                                    if k not in ("failed_accounts", "blocked_accounts")
                                }
                            ),
                        )
                        return
                    if result.get("blocked_accounts"):
                        self.store.sync_status(
                            "gmail",
                            "error",
                            "A Gmail account needs attention. Reconnect it in Sources; completed imports are preserved.",
                        )
                        return
                    self.store.sync_status(
                        "gmail",
                        "running",
                        "Google temporarily slowed the import. Saved progress will resume automatically.",
                    )
                    await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.store.sync_status(
                    "gmail",
                    "paused",
                    "Import paused when Meridian closed. It will resume next launch.",
                )
                raise
            except Exception:
                self.store.sync_status(
                    "gmail",
                    "error",
                    "Import paused. Check your connection, then resume in Sources. Saved progress is preserved.",
                )

    async def stop(self):
        if self.running():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def resume_needed(self):
        with self.store.db() as db:
            row = db.execute("SELECT status FROM syncs WHERE source='gmail'").fetchone()
            unfinished = db.execute(
                "SELECT 1 FROM gmail_progress WHERE state IN ('running','paused') LIMIT 1"
            ).fetchone()
        return bool((row and row[0] in ("running", "paused")) or unfinished)

    def attach(self, app):
        @app.post("/api/sync/start", status_code=202)
        async def start_async():
            return self.start()

        @app.get("/api/sync/progress")
        def progress():
            with self.store.db() as db:
                accounts = [
                    dict(r)
                    for r in db.execute(
                        "SELECT p.*,(SELECT count(*) FROM gmail_checkpoint c WHERE c.account=p.account AND c.mode=p.mode) AS saved_messages FROM gmail_progress p"
                    )
                ]
                status = db.execute(
                    "SELECT * FROM syncs WHERE source='gmail'"
                ).fetchone()
            return {
                "running": self.running(),
                "query": os.getenv("GMAIL_QUERY", GMAIL_QUERY),
                "accounts": accounts,
                "sync": dict(status) if status else None,
            }
