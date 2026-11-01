import pytest
from fastapi.testclient import TestClient
from meridian.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "api.db")
    with TestClient(app) as c:
        c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
        yield c


def test_demo_is_explicit_and_isolated(client):
    assert len(client.get("/api/state?demo=true").json()["tasks"]) == 8
    assert client.get("/api/state").json()["tasks"] == []


def test_review_confirm_and_completion_persist(client):
    r = client.post(
        "/api/import", json={"text": "Homework due next Friday", "course": "Math"}
    )
    assert r.status_code == 200 and r.json()["created"] == 1
    t = client.get("/api/state").json()["tasks"][0]
    assert t["due_at"] is None and t["confidence"] == "review"
    assert (
        client.patch(f'/api/tasks/{t["id"]}', json={"confirm": True}).status_code == 422
    )
    assert (
        client.patch(
            f'/api/tasks/{t["id"]}',
            json={
                "confirm": True,
                "due_at": "2026-11-06T23:59:00-05:00",
                "completed": True,
            },
        ).status_code
        == 200
    )
    task = client.get("/api/state").json()["tasks"][0]
    assert task["completed"] and task["confidence"] == "confirmed"
    assert task["evidence"][0]["quote"] == "Homework due next Friday"
    assert task["changes"]


def test_invalid_inputs(client):
    assert client.post("/api/import", json={"text": ""}).status_code == 422
    assert (
        client.post(
            "/api/import",
            json={
                "text": "Homework due 2026-11-03 23:59",
                "url": "javascript:alert(1)",
            },
        ).status_code
        == 422
    )
    assert client.patch("/api/tasks/9999", json={"completed": True}).status_code == 404
    assert (
        client.post(
            "/api/blocks",
            json={"title": "Busy", "start": "2026-11-01T09:00:00", "minutes": 60},
        ).status_code
        == 422
    )


def test_token_origin_host_protection(client):
    h = dict(client.headers)
    client.headers.pop("X-Meridian-Token")
    assert client.post("/api/plan").status_code == 403
    client.headers.update(h)
    assert (
        client.post("/api/plan", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 403
    assert (
        "frame-ancestors 'none'" in client.get("/").headers["Content-Security-Policy"]
    )


def test_busy_conflict_and_removal(client):
    body = {
        "title": "Lecture",
        "start": "2026-11-02T09:00:00-05:00",
        "minutes": 60,
        "kind": "busy",
    }
    assert client.post("/api/blocks", json=body).status_code == 200
    assert client.post("/api/blocks", json=body).status_code == 409
    bid = client.get("/api/state").json()["blocks"][0]["id"]
    assert client.delete(f"/api/blocks/{bid}").status_code == 200
    assert not client.get("/api/state").json()["blocks"]


def test_ics_excludes_uncertain_and_uses_stable_uids(client):
    client.post(
        "/api/import",
        json={
            "text": "Quiz next week\nHomework due 2026-11-02 23:59",
            "course": "Math",
        },
    )
    r = client.get("/api/calendar.ics")
    assert r.status_code == 200
    assert r.text.count("BEGIN:VEVENT") == 1
    assert "SUMMARY:Homework" in r.text
    assert "UID:task-" in r.text
    assert r.text == client.get("/api/calendar.ics").text


def test_failed_sync_preserves_tasks_and_sanitizes(client, monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "test-token")
    async def fail():
        raise RuntimeError("super-secret-token https://provider.example/private")

    monkeypatch.setattr("meridian.app.canvas_sync", fail)
    monkeypatch.setattr("meridian.app.gmail_sync", fail)
    client.post("/api/import", json={"text": "Homework due 2026-11-02 23:59"})
    r = client.post("/api/sync")
    assert r.status_code == 200
    assert all(v["status"] == "error" for v in r.json().values())
    assert "super-secret" not in r.text
    assert len(client.get("/api/state").json()["tasks"]) == 1


def test_manual_canvas_workflow_skips_unconfigured_api(client, monkeypatch):
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)

    async def canvas():
        pytest.fail("Manual import must not call Canvas")

    async def gmail():
        return []

    monkeypatch.setattr("meridian.app.canvas_sync", canvas)
    monkeypatch.setattr("meridian.app.gmail_sync", gmail)
    result = client.post("/api/sync").json()
    assert result["canvas"]["status"] == "skipped"
    assert result["gmail"]["status"] == "ok"


def test_syllabus_deadline_can_be_changed_without_losing_evidence(client):
    text = "Problem set 7 due 2026-11-02 23:59 on Gradescope"
    client.post("/api/import", json={"text": text, "course": "CS 2800", "kind": "syllabus", "url": "https://canvas.cornell.edu/courses/123"})
    original = client.get("/api/state").json()["tasks"][0]
    result = client.patch("/api/tasks/" + str(original["id"]), json={"due_at": "2026-11-05T17:00:00-05:00", "confirm": True})
    assert result.status_code == 200
    changed = client.get("/api/state").json()["tasks"][0]
    assert changed["id"] == original["id"]
    assert changed["evidence"] == original["evidence"]
    assert changed["confidence"] == "confirmed"
    assert changed["due_at"].startswith("2026-11-05T17:00")
    calendar = client.get("/api/calendar.ics").text
    assert "20261105T220000Z" in calendar
    assert "20261103T045900Z" not in calendar


def test_manual_task(client):
    r = client.post(
        "/api/tasks",
        json={
            "title": "Prepare interview",
            "category": "career",
            "source_id": "manual:1",
            "source_type": "manual",
            "evidence": "User created",
            "destination": "Personal",
            "minutes": 30,
        },
    )
    assert r.status_code == 200
    t = client.get("/api/state").json()["tasks"][0]
    assert t["title"] == "Prepare interview" and t["confidence"] == "review"


def test_plan_does_not_change_deadlines(client):
    before = {
        t["id"]: t["due_at"] for t in client.get("/api/state?demo=true").json()["tasks"]
    }
    assert client.post("/api/plan?demo=true").status_code == 200
    after = {
        t["id"]: t["due_at"] for t in client.get("/api/state?demo=true").json()["tasks"]
    }
    assert before == after


def test_completion_clears_work_block_but_preserves_busy(client):
    from datetime import datetime, timedelta, timezone

    future = datetime.now(timezone.utc) + timedelta(days=3)
    client.post(
        "/api/tasks",
        json={
            "title": "Finish work",
            "due_at": future.isoformat(),
            "confidence": "confirmed",
            "source_type": "manual",
            "source_id": "manual:x",
            "evidence": "User",
        },
    )
    task = client.get("/api/state").json()["tasks"][0]
    start = (future - timedelta(days=1)).isoformat()
    assert (
        client.post(
            "/api/blocks",
            json={
                "task_id": task["id"],
                "title": "Focus",
                "start": start,
                "minutes": 30,
            },
        ).status_code
        == 200
    )
    client.patch(f'/api/tasks/{task["id"]}', json={"completed": True})
    assert client.get("/api/state").json()["blocks"] == []
    assert (
        client.post(
            "/api/blocks",
            json={
                "task_id": task["id"],
                "title": "Focus",
                "start": start,
                "minutes": 30,
            },
        ).status_code
        == 422
    )
