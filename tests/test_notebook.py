import copy
import json
import sqlite3
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from meridian.app import create_app
from meridian.store import Store
from meridian import notebook, journal
from meridian.extract import TZ


def daybook():
    return {
        "version": 1,
        "tasks": [
            {
                "id": "old",
                "title": "A completed task",
                "category": "Projects",
                "createdAt": "2026-10-10T12:00:00-04:00",
                "completedAt": "2026-10-20T00:00:00Z",
                "dateOnlyCompletion": True,
                "unknownCreatedAt": True,
                "effort": 25,
                "sourceHint": "Original hint",
            },
            {
                "id": "open",
                "title": "Weekly practice",
                "category": "LeetCode / coding",
                "due": "2026-10-20",
                "repeat": "weekly",
                "effort": 0,
                "importance": 3,
                "createdAt": "2026-10-10T12:00:00-04:00",
            },
            {
                "id": "deleted",
                "title": "Recover me",
                "category": "Personal",
                "deletedAt": "2026-10-21T12:00:00Z",
            },
            {
                "id": "reference",
                "recordType": "reference",
                "title": "Companies",
                "category": "Internships / jobs",
                "sourceHint": "Keep me",
            },
            {
                "id": "reminder",
                "title": "Check applications",
                "surface": "internships",
                "completedAt": "2026-10-20T12:00:00Z",
                "effort": 15,
            },
            {
                "id": "event-task",
                "title": "Exam",
                "category": "Academics / classes",
                "due": "2026-11-01",
                "calendarEventId": "exam",
            },
        ],
        "references": [
            {
                "title": "Resources",
                "items": ["One", {"label": "Two", "url": "https://example.com"}],
            }
        ],
        "calendarEvents": [
            {
                "id": "exam",
                "title": "Exam",
                "course": "TEST 101",
                "date": "2026-11-01",
                "time": "10:00",
                "endTime": "11:00",
                "location": "Room A",
            },
            {
                "id": "break",
                "title": "Break",
                "date": "2026-11-02",
                "endDate": "2026-11-04",
                "kind": "break",
            },
        ],
        "calendarCadences": [
            {
                "id": "weekly",
                "course": "TEST 101",
                "title": "Practice",
                "weekdays": [1, 3],
            }
        ],
        "migrations": {"original": "retained"},
    }


def test_lossless_merge_idempotency_history_and_date_only(tmp_path):
    store = Store(tmp_path / "meridian.db")
    payload = daybook()
    result = notebook.import_daybook(store, payload)
    assert result == dict(
        tasks=4, completions=2, reminders=1, notes=2, events=2, cadences=1, deleted=1
    )
    assert notebook.import_daybook(store, payload)["already_imported"]
    assert len(store.tasks()) == 3
    assert len(notebook.history(store)) == 2
    assert notebook.notes(store)[0]["items"] or notebook.notes(store)[1]["items"]
    with store.db() as db:
        task = db.execute("SELECT * FROM tasks WHERE notebook_id='old'").fetchone()
        assert (
            task["completed_at"] == "2026-10-20T00:00:00Z"
            and task["unknown_created_at"] == 1
        )
        assert task["due_at"] is None
        assert (
            json.loads(
                db.execute(
                    "SELECT data FROM daybook_records WHERE kind='root'"
                ).fetchone()[0]
            )
            == payload
        )
        assert db.execute(
            "SELECT linked_task_id FROM calendar_events WHERE title='Exam'"
        ).fetchone()[0]
    assert len(list((tmp_path / "Backups").glob("*.db"))) == 1
    assert len(list((tmp_path / "Backups").glob("Daybook-original-*.json"))) == 1
    review = journal.review(
        store, week=datetime(2026, 10, 20).date(), now=datetime(2026, 10, 29, tzinfo=TZ)
    )
    assert next(d for d in review["days"] if d["date"] == "2026-10-20")["count"] == 2
    assert next(d for d in review["days"] if d["date"] == "2026-10-19")["count"] == 0
    assert review["unknown_created"] == 1
    payload["imports"] = ["new provenance"]
    notebook.import_daybook(store, payload)
    assert len(store.tasks()) == 3 and len(notebook.history(store)) == 2


def test_repeat_completion_reopen_chain_and_future_guard(tmp_path):
    store = Store(tmp_path / "tasks.db")
    today = datetime.now(TZ).date()
    identifier = notebook.add_task(
        store,
        {"title": "Practice", "repeat_rule": "weekly", "due_date": today.isoformat()},
    )

    def complete(id, done, at=None):
        with store.db() as db:
            task = db.execute("SELECT * FROM tasks WHERE id=?", (id,)).fetchone()
            notebook.complete_task(db, task, done, at)
            journal.record_task(db, id, done, at)
            db.execute("UPDATE tasks SET completed=? WHERE id=?", (done, id))

    complete(identifier, True)
    complete(identifier, True)
    tasks = store.tasks()
    assert len(tasks) == 2
    child = next(t for t in tasks if t["parent_id"] == identifier)
    assert child["due_date"] == (today + timedelta(days=7)).isoformat()
    with pytest.raises(ValueError, match="later day"):
        complete(child["id"], True)
    complete(identifier, False)
    assert len(store.tasks()) == 1 and not notebook.history(store)
    complete(identifier, True)
    child = next(t for t in store.tasks() if t["parent_id"] == identifier)
    complete(child["id"], True, (datetime.now(TZ) + timedelta(days=8)).isoformat())
    with pytest.raises(ValueError, match="most recent"):
        complete(identifier, False)


def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_SETTINGS_DIR", str(tmp_path / "settings"))
    app = create_app(tmp_path / "api.db")
    c = TestClient(app)
    c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
    return c, app.state.store


def test_notebook_api_calendar_track_backup_restore(tmp_path, monkeypatch):
    c, store = client(tmp_path, monkeypatch)
    r = c.post(
        "/api/notebook/tasks",
        json={"title": "Date-only task", "due_date": "2026-11-05", "minutes": 0},
    )
    assert r.status_code == 200
    task_id = r.json()["id"]
    ics = c.get("/api/calendar.ics").text
    assert "DTSTART;VALUE=DATE:20261105" in ics
    assert (
        c.post(
            "/api/notebook/tasks", json={"title": "Bad date", "due_date": "2026-02-30"}
        ).status_code
        == 422
    )
    event = {
        "title": "Confirmed exam",
        "date": "2026-11-10",
        "time": "13:00",
        "end_time": "14:00",
    }
    eid = c.post("/api/calendar-events", json=event).json()["id"]
    tracked = c.post(f"/api/calendar-events/{eid}/track").json()["id"]
    assert c.post(f"/api/calendar-events/{eid}/track").json() == {
        "id": tracked,
        "existing": True,
    }
    assert (
        c.post("/api/calendar-events", json={**event, "time": "29:00"}).status_code
        == 422
    )
    assert (
        c.post(
            "/api/calendar-events", json={**event, "end_date": "2026-01-01"}
        ).status_code
        == 422
    )
    tentative = c.post(
        "/api/calendar-events", json={**event, "tentative": True}
    ).json()["id"]
    assert c.post(f"/api/calendar-events/{tentative}/track").status_code == 422
    c.delete(f"/api/notebook/tasks/{task_id}")
    assert c.get("/api/notebook").json()["trash"][0]["id"] == task_id
    assert c.post(f"/api/notebook/tasks/{task_id}/restore").status_code == 200
    backup = c.get("/api/backup").json()
    assert not any("token" in table.lower() for table in backup["tables"])
    c.post("/api/notebook/tasks", json={"title": "Added after backup"})
    assert c.post("/api/backup/restore", json=backup).status_code == 200
    assert not any(t["title"] == "Added after backup" for t in store.tasks())
    corrupt = copy.deepcopy(backup)
    corrupt["tables"]["tasks"][0]["identity"] = None
    assert c.post("/api/backup/restore", json=corrupt).status_code == 422
    assert notebook.export_notebook(store)["tables"] == backup["tables"]
    assert (
        c.post(
            "/api/reference-notes",
            json={"title": "Lists", "items": [{"label": "Saved object"}]},
        ).status_code
        == 200
    )


def test_import_rollback_and_cadence_validation(tmp_path, monkeypatch):
    c, store = client(tmp_path, monkeypatch)
    before = notebook.export_notebook(store)["tables"]
    broken = daybook()
    broken["tasks"][1]["due"] = "invalid"
    assert c.post("/api/daybook/import", json=broken).status_code == 422
    assert notebook.export_notebook(store)["tables"] == before
    cadence = {
        "title": "Check homework",
        "course": "TEST",
        "start": "2026-10-01",
        "end": "2026-12-01",
        "weekdays": [1, 3],
    }
    result = c.post("/api/calendar-cadences", json=cadence)
    assert result.status_code == 200
    assert (
        c.post("/api/calendar-cadences", json={**cadence, "weekdays": [9]}).status_code
        == 422
    )
    assert c.delete("/api/calendar-cadences/" + result.json()["id"]).status_code == 200


def test_timed_notebook_edits_and_historical_reminder_guard(tmp_path, monkeypatch):
    c, store = client(tmp_path, monkeypatch)
    data = {
        "title": "Timed task",
        "due_date": "2026-11-10",
        "due_at": "2026-11-10T13:00:00-05:00",
    }
    task = c.post("/api/notebook/tasks", json=data).json()["id"]
    assert (
        c.put(
            f"/api/notebook/tasks/{task}", json={**data, "notes": "Kept time"}
        ).status_code
        == 200
    )
    saved = next(t for t in store.tasks() if t["id"] == task)
    assert saved["due_at"] == data["due_at"] and saved["due_date"] is None
    assert (
        c.patch(f"/api/tasks/{task}", json={"clear_deadline": True}).status_code == 200
    )
    assert next(t for t in store.tasks() if t["id"] == task)["due_at"] is None
    rid = c.post("/api/reminders", json={"title": "Reusable check-in"}).json()["id"]
    c.post(f"/api/reminders/{rid}/action", json={"action": "complete"})
    event = next(
        e for e in c.get("/api/notebook").json()["history"] if e["kind"] == "reminder"
    )
    c.post(f"/api/reminders/{rid}/action", json={"action": "rearm"})
    c.post(f"/api/reminders/{rid}/action", json={"action": "complete"})
    assert c.post(f'/api/activity/{event["id"]}/reopen').status_code == 409
    assert (
        len(
            [
                e
                for e in c.get("/api/notebook").json()["history"]
                if e["kind"] == "reminder"
            ]
        )
        == 2
    )


def test_review_candidates_do_not_inflate_daybook_workload(tmp_path):
    from meridian.models import Candidate

    store = Store(tmp_path / "review.db")
    notebook.add_task(store, {"title": "Real task", "notebook_category": "Projects"})
    store.ingest(
        [
            Candidate(
                title="Review suggestion",
                course="Gmail",
                evidence="An uncertain email",
                source_type="gmail",
                source_id="mail:test",
                confidence="review",
            )
        ]
    )
    review = journal.review(store)
    assert review["totals"]["open"] == 1 and review["review_count"] == 1
    assert len(review["unfinished"]) == 1


def test_invalid_event_ranges_and_backup_roots_are_rejected(tmp_path, monkeypatch):
    c, store = client(tmp_path, monkeypatch)
    assert c.post("/api/backup/restore", json=[]).status_code == 422
    assert c.post("/api/daybook/import", json=[]).status_code == 422
    assert (
        c.post(
            "/api/calendar-events", json={"title": "Missing day", "date": ""}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/calendar-events",
            json={
                "title": "Backwards",
                "date": "2026-11-01",
                "time": "14:00",
                "end_time": "13:00",
            },
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/calendar-events",
            json={"title": "Missing start", "date": "2026-11-01", "end_time": "13:00"},
        ).status_code
        == 422
    )
    future = (datetime.now(TZ) + timedelta(days=3)).isoformat()
    identifier = c.post(
        "/api/notebook/tasks",
        json={"title": "Future repeat", "due_at": future, "repeat_rule": "daily"},
    ).json()["id"]
    assert (
        c.patch(f"/api/tasks/{identifier}", json={"completed": True}).status_code == 409
    )
