from datetime import datetime
import sqlite3
import pytest
from fastapi.testclient import TestClient
from meridian.app import create_app
from meridian import journal
from meridian.extract import TZ
from meridian.models import Candidate
from meridian.store import Store


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workspace.db")
    with TestClient(app) as c:
        c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
        yield c


def new_reminder(client, **kw):
    return client.post(
        "/api/reminders", json={"title": "Application check-in", "minutes": 20, **kw}
    ).json()["id"]


def action(client, rid, act, demo=False):
    return client.post(
        f"/api/reminders/{rid}/action?demo={str(demo).lower()}", json={"action": act}
    )


def test_reusable_checkins_keep_history_without_duplicate_completions(client):
    rid = new_reminder(client)
    assert action(client, rid, "complete").status_code == 200
    action(client, rid, "complete")
    r = client.get("/api/weekly-review").json()
    assert r["totals"]["checkins"] == 1 and r["totals"]["minutes"] == 20
    assert action(client, rid, "rearm").status_code == 200
    action(client, rid, "rearm")
    reminder = client.get("/api/state").json()["reminders"][0]
    assert (
        reminder["cycle"] == 1
        and reminder["completions"] == 1
        and reminder["completed_at"] is None
    )
    action(client, rid, "complete")
    assert client.get("/api/weekly-review").json()["totals"]["checkins"] == 2
    action(client, rid, "undo")
    assert client.get("/api/weekly-review").json()["totals"]["checkins"] == 1
    action(client, rid, "complete")
    assert client.get("/api/weekly-review").json()["totals"]["checkins"] == 2


def test_editing_reminder_does_not_rewrite_previous_activity(client):
    rid = new_reminder(client)
    action(client, rid, "complete")
    assert (
        client.put(
            f"/api/reminders/{rid}",
            json={"title": "Renamed", "minutes": 60, "category": "personal"},
        ).status_code
        == 200
    )
    event = client.get("/api/weekly-review").json()["events"][0]
    assert (
        event["title"] == "Application check-in"
        and event["minutes"] == 20
        and event["category"] == "career"
    )
    reminder = client.get("/api/state").json()["reminders"][0]
    assert reminder["title"] == "Renamed" and reminder["minutes"] == 60


def test_archive_and_restore_preserve_history_and_reject_actions(client):
    rid = new_reminder(client)
    action(client, rid, "complete")
    action(client, rid, "archive")
    assert action(client, rid, "rearm").status_code == 409
    assert client.get("/api/weekly-review").json()["totals"]["checkins"] == 1
    assert action(client, rid, "restore").status_code == 200
    assert action(client, rid, "rearm").status_code == 200
    assert not client.get("/api/state").json()["reminders"][0]["archived"]


def test_reminders_are_workspace_scoped_and_inputs_validated(client):
    assert not client.get("/api/state").json()["reminders"]
    examples = client.get("/api/state?demo=true").json()["reminders"]
    assert len(examples) == 3
    rid = examples[0]["id"]
    assert action(client, rid, "complete").status_code == 404
    assert (
        client.put(
            f"/api/reminders/{rid}", json={"title": "Wrong workspace"}
        ).status_code
        == 404
    )
    assert action(client, rid, "complete", True).status_code == 200
    assert not client.get("/api/weekly-review").json()["events"]
    assert client.post("/api/reminders", json={"title": "   "}).status_code == 422
    assert (
        client.post(
            "/api/reminders", json={"title": "Test", "due_at": "2026-10-28T10:00:00"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/reminders", json={"title": "Test", "minutes": 0}).status_code
        == 422
    )
    assert action(client, 9999, "complete").status_code == 404
    assert action(client, rid, "invalid").status_code == 422


def test_rearming_clears_expired_date(client):
    rid = new_reminder(client, due_at="2026-10-25T10:00:00-04:00")
    action(client, rid, "complete")
    action(client, rid, "rearm")
    assert client.get("/api/state").json()["reminders"][0]["due_at"] is None


def test_task_completion_reopen_and_estimate_snapshot(client):
    client.post(
        "/api/tasks",
        json={
            "title": "Homework",
            "source_type": "manual",
            "source_id": "manual:test",
            "evidence": "User",
            "minutes": 90,
            "category": "academic",
        },
    )
    tid = client.get("/api/state").json()["tasks"][0]["id"]
    client.patch(f"/api/tasks/{tid}", json={"completed": True})
    client.patch(f"/api/tasks/{tid}", json={"completed": True, "minutes": 10})
    review = client.get("/api/weekly-review").json()
    assert review["totals"]["tasks"] == 1 and review["totals"]["minutes"] == 90
    client.patch(f"/api/tasks/{tid}", json={"completed": False})
    assert client.get("/api/weekly-review").json()["totals"]["completed"] == 0
    client.patch(f"/api/tasks/{tid}", json={"completed": True})
    assert client.get("/api/weekly-review").json()["totals"]["minutes"] == 10


def test_upstream_completion_records_once(tmp_path):
    store = Store(tmp_path / "canvas.db")
    task = Candidate(
        title="HW",
        course="CS",
        source_id="canvas:1",
        source_type="assignment",
        evidence="Submitted",
        submitted=True,
    )
    store.ingest([task])
    store.ingest([task])
    r = journal.review(store)
    assert r["totals"]["tasks"] == 1


def test_week_boundaries_use_application_timezone_and_exclude_future_events(tmp_path):
    store = Store(tmp_path / "week.db")
    with store.db() as db:
        for i, at in enumerate(
            [
                "2026-11-02T02:00:00+00:00",
                "2026-11-02T06:00:00+00:00",
                "2026-11-09T05:00:00+00:00",
            ]
        ):
            db.execute(
                "INSERT INTO activity(kind,entity_id,cycle,title,category,minutes,completed_at,demo) VALUES('reminder',?,0,'Check-in','career',15,?,0)",
                (i, at),
            )
    r = journal.review(
        store, datetime(2026, 11, 4).date(), now=datetime(2026, 11, 5, 12, tzinfo=TZ)
    )
    assert r["week_start"] == "2026-11-02" and r["week_end"] == "2026-11-08"
    assert r["totals"]["completed"] == 1
    assert r["days"][0]["count"] == 1
    assert r["days"][-1]["future"] and r["days"][-1]["count"] == 0


def test_reflections_normalize_week_and_persist_separately(client):
    notes = {
        "wins": "A small win",
        "friction": "Too many tabs",
        "next_focus": "One focused block",
    }
    assert (
        client.put("/api/weekly-review/2026-10-28", json=notes).json()["week_start"]
        == "2026-10-26"
    )
    assert (
        client.get("/api/weekly-review?week=2026-10-30").json()["notes"]["wins"]
        == "A small win"
    )
    assert (
        client.get("/api/weekly-review?week=2026-11-02").json()["notes"]["wins"] == ""
    )
    assert (
        client.get("/api/weekly-review?week=2026-10-28&demo=true").json()["notes"][
            "wins"
        ]
        == ""
    )
    assert (
        client.put(
            "/api/weekly-review/2026-10-28", json={"wins": "x" * 4001}
        ).status_code
        == 422
    )
    assert client.get("/api/weekly-review?week=invalid").status_code == 422


def test_schema_upgrade_keeps_existing_tasks_and_reminders_persist(tmp_path):
    path = tmp_path / "upgrade.db"
    store = Store(path)
    store.ingest(
        [
            Candidate(
                title="Existing task",
                course="Math",
                source_type="manual",
                source_id="old:1",
                evidence="Existing source",
            )
        ]
    )
    with store.db() as db:
        db.executescript(
            "DROP TABLE reminders; DROP TABLE activity; DROP TABLE weekly_notes;"
        )
    app = create_app(path)
    with TestClient(app) as c:
        c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
        rid = new_reminder(c)
        action(c, rid, "complete")
    reopened = create_app(path)
    with TestClient(reopened) as c:
        state = c.get("/api/state").json()
        assert state["tasks"][0]["title"] == "Existing task"
        assert state["reminders"][0]["completions"] == 1
        assert c.get("/api/weekly-review").json()["totals"]["checkins"] == 1


def test_new_endpoints_require_write_token(client):
    client.headers.pop("X-Meridian-Token")
    assert client.post("/api/reminders", json={"title": "No token"}).status_code == 403
    assert client.put("/api/weekly-review/2026-10-26", json={}).status_code == 403
