import asyncio
import base64
import httpx
import pytest
from meridian.connectors import gmail_account_sync
from meridian.store import Store


def test_interrupted_import_resumes_without_refetching_committed_messages(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "checkpoint.db")
    fetched = []
    fail = True

    def handler(request):
        nonlocal fail
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "a"}, {"id": "b"}]})
        message = request.url.path.rsplit("/", 1)[1]
        fetched.append(message)
        if message == "b" and fail:
            return httpx.Response(
                403, json={"error": {"errors": [{"reason": "insufficientPermissions"}]}}
            )
        return httpx.Response(
            200,
            json={
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            f"Please complete interview {message} by 2026-11-04 12:00".encode()
                        ).decode()
                    },
                }
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.connectors.httpx.AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            gmail_account_sync(token="test", email="first@example.com", store=store)
        )
    assert len(store.tasks()) == 1
    fail = False
    result = asyncio.run(
        gmail_account_sync(token="test", email="first@example.com", store=store)
    )
    assert fetched == ["a", "b", "b"]
    assert result["cached"] == 1
    assert result["created"] == 1
    assert len(store.tasks()) == 2
    # A second account must fetch its own messages, even when IDs match.
    asyncio.run(
        gmail_account_sync(token="test", email="second@example.com", store=store)
    )
    assert fetched[-2:] == ["a", "b"]


def test_nonactionable_messages_are_checkpointed_without_storing_bodies(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "empty.db")
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return (
            httpx.Response(200, json={"messages": [{"id": "a"}]})
            if request.url.path.endswith("/messages")
            else httpx.Response(
                200,
                json={
                    "payload": {
                        "mimeType": "text/plain",
                        "body": {
                            "data": base64.urlsafe_b64encode(
                                b"A pleasant greeting"
                            ).decode()
                        },
                    }
                },
            )
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.connectors.httpx.AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    for _ in range(2):
        asyncio.run(
            gmail_account_sync(token="test", email="first@example.com", store=store)
        )
    assert len(requests) == 3
    assert store.tasks() == []
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM gmail_checkpoint").fetchone()[0] == 1
        assert {r[1] for r in db.execute("PRAGMA table_info(gmail_checkpoint)")} == {
            "account",
            "message_id",
            "mode",
            "processed_at",
        }


def test_background_job_cancellation_preserves_resume_marker(tmp_path, monkeypatch):
    from meridian.sync_jobs import SyncJobs

    store = Store(tmp_path / "background.db")
    monkeypatch.setenv("GOOGLE_ACCOUNTS", '{"first@example.com":"test"}')
    entered = asyncio.Event()

    async def stalled(store):
        store.gmail_progress(
            "first@example.com", "newer_than:30d", processed=12, cached=4
        )
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("meridian.sync_jobs.gmail_sync", stalled)

    async def exercise():
        job = SyncJobs(store, asyncio.Lock())
        assert job.start()["status"] == "running"
        await entered.wait()
        assert job.start()["status"] == "running"
        await job.stop()
        assert not job.running() and job.resume_needed()

    asyncio.run(exercise())
    store.gmail_progress("first@example.com", "newer_than:30d", state="paused")
    with store.db() as db:
        progress = db.execute("SELECT * FROM gmail_progress").fetchone()
        assert progress["processed"] == 12 and progress["cached"] == 4
        assert (
            db.execute("SELECT status FROM syncs WHERE source='gmail'").fetchone()[0]
            == "paused"
        )


def test_background_completes_and_permission_error_does_not_retry(
    tmp_path, monkeypatch
):
    from meridian.sync_jobs import SyncJobs

    store = Store(tmp_path / "complete.db")
    monkeypatch.setenv("GOOGLE_ACCOUNTS", '{"first@example.com":"test"}')
    responses = [
        {"created": 1, "partial": False},
        {"partial": True, "blocked_accounts": ["first@example.com"]},
    ]

    async def sync(store):
        return responses.pop(0)

    monkeypatch.setattr("meridian.sync_jobs.gmail_sync", sync)

    async def exercise():
        job = SyncJobs(store, asyncio.Lock())
        job.start()
        await job.task
        with store.db() as db:
            assert (
                db.execute("SELECT status FROM syncs WHERE source='gmail'").fetchone()[
                    0
                ]
                == "ok"
            )
        job.start()
        await job.task
        with store.db() as db:
            assert (
                db.execute("SELECT status FROM syncs WHERE source='gmail'").fetchone()[
                    0
                ]
                == "error"
            )

    asyncio.run(exercise())
