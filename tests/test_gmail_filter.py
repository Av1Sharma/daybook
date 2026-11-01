from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from meridian.gmail_filter import interview_candidates, retire_legacy_suggestions
from meridian.store import Store
from meridian.models import Candidate
from meridian.notebook import add_task

RECEIVED = datetime(2026, 10, 20, 12, tzinfo=ZoneInfo("America/New_York"))


@pytest.mark.parametrize(
    "subject,body",
    [
        (
            "Application received",
            "Thank you for applying. We will contact you about interviews.",
        ),
        (
            "Interview update",
            "Unfortunately, we will not be moving forward. Respond by November 4, 2026.",
        ),
        ("Interview invitation", "Please schedule your interview using this link."),
        (
            "Coding assessment",
            "Please complete the coding assessment by November 4, 2026.",
        ),
        (
            "Newsletter: interview tips",
            "Please join our interview workshop on November 4, 2026.",
        ),
        ("Hello", "Please reply by November 4, 2026."),
        (
            "Your application",
            "We may invite you to interview later. Application received.",
        ),
        (
            "Re: Interview invitation",
            "Thanks!\nOn Tuesday wrote:\nPlease complete your interview by November 4, 2026.",
        ),
        ("Interview invitation", "Please schedule your interview by tomorrow."),
        (
            "Interview invitation",
            "Please complete your interview by February 30, 2026.",
        ),
    ],
)
def test_nonqualifying_emails_never_become_review_tasks(subject, body):
    assert interview_candidates(subject, body, received=RECEIVED) == []


@pytest.mark.parametrize(
    "subject,body,expected",
    [
        (
            "Interview invitation",
            "Please complete your recorded interview by November 4, 2026.",
            "2026-11-04",
        ),
        (
            "Schedule your interview",
            "Please select an interview slot by Oct 31.",
            "2026-10-31",
        ),
        (
            "Interview confirmed",
            "Your interview is scheduled for 4 November 2026 at 2:30 PM ET.",
            "2026-11-04",
        ),
        (
            "Interview invitation",
            "Please schedule your interview by 11/05/2026.",
            "2026-11-05",
        ),
        (
            "Interview invitation",
            "Please complete your interview by 2026-11-04T12:00:00Z.",
            "2026-11-04",
        ),
    ],
)
def test_qualifying_message_has_one_confirmed_dated_task(subject, body, expected):
    result = interview_candidates(
        subject, body, source_id="gmail:a:message", received=RECEIVED
    )
    assert len(result) == 1
    item = result[0]
    assert (
        item.confidence == "confirmed"
        and item.category == "career"
        and item.minutes == 0
    )
    assert (
        item.due_date.isoformat() if item.due_date else item.due_at.date().isoformat()
    ) == expected
    assert item.source_id == "gmail:a:message:interview-deadline"
    assert body in item.evidence


def test_date_only_missing_year_and_timezone_are_preserved():
    assert (
        interview_candidates(
            "Interview invitation", "Please complete your interview by November 4."
        )
        == []
    )
    date_only = interview_candidates(
        "Interview invitation",
        "Please complete your interview by November 4.",
        received=RECEIVED,
    )[0]
    assert date_only.due_at is None and date_only.due_date.isoformat() == "2026-11-04"
    timed = interview_candidates(
        "Interview confirmed",
        "Your interview is scheduled for November 4, 2026 at 2:30 PM PT.",
        received=RECEIVED,
    )[0]
    assert (
        timed.due_at.hour == 14
        and timed.due_at.utcoffset().total_seconds() == -8 * 3600
    )
    iso = interview_candidates(
        "Interview invitation",
        "Please complete your interview by 2026-11-04T12:00:00Z.",
        received=RECEIVED,
    )[0]
    assert iso.due_at.utcoffset().total_seconds() == 0


def test_store_and_cleanup_keep_daybook_manual_and_course_records(tmp_path):
    store = Store(tmp_path / "filter.db")
    old = Candidate(
        title="Old mailbox noise",
        course="Gmail",
        source_type="gmail",
        source_id="gmail:old",
        evidence="Please do not reply",
    )
    store.ingest([old])
    add_task(store, {"title": "DayBook work"})
    store.ingest(
        [
            Candidate(
                title="Course task",
                course="CS",
                source_type="syllabus",
                source_id="course",
                evidence="Homework due soon",
            )
        ]
    )
    reviewed = old.model_copy(
        update={"title": "User-reviewed email", "source_id": "gmail:reviewed"}
    )
    store.ingest([reviewed])
    with store.db() as db:
        tid = db.execute(
            "SELECT id FROM tasks WHERE title='User-reviewed email'"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO changes(task_id,message,created_at) VALUES(?,'Manual update: confirmed','2026-10-20')",
            (tid,),
        )
    assert retire_legacy_suggestions(store) == 1
    assert retire_legacy_suggestions(store) == 0
    assert {t["title"] for t in store.tasks()} == {
        "DayBook work",
        "Course task",
        "User-reviewed email",
    }
    assert len(list((tmp_path / "Backups").glob("*.db"))) == 1
    item = interview_candidates(
        "Interview invitation",
        "Please complete your interview by November 4, 2026.",
        source_id="gmail:a:m",
    )[0]
    store.ingest([item])
    store.ingest([item])
    saved = [t for t in store.tasks() if t["title"] == "Interview invitation"]
    assert (
        len(saved) == 1
        and saved[0]["due_date"] == "2026-11-04"
        and saved[0]["confidence"] == "confirmed"
    )


def test_recruiter_notification_timeline_is_not_the_users_deadline():
    assert (
        interview_candidates(
            "Program recruiting timeline",
            "All candidates invited to interview will be notified by 11/04, and we cannot accelerate the process.",
            received=RECEIVED,
        )
        == []
    )


def test_gmail_manual_import_and_optional_ai_cannot_bypass_filter(
    tmp_path, monkeypatch
):
    import asyncio
    from fastapi.testclient import TestClient
    from meridian.app import create_app
    from meridian.extract import extract_ai

    monkeypatch.setenv("MERIDIAN_SETTINGS_DIR", str(tmp_path / "settings"))
    app = create_app(tmp_path / "api.db")
    c = TestClient(app)
    c.headers["X-Meridian-Token"] = c.get("/api/state").json()["token"]
    assert (
        c.post(
            "/api/import",
            json={
                "kind": "gmail",
                "text": "Interview invitation\nPlease schedule your interview soon.",
            },
        ).json()["candidates"]
        == 0
    )
    result = c.post(
        "/api/import",
        json={
            "kind": "gmail",
            "text": "Interview invitation\nPlease complete your video interview by November 4, 2026.",
        },
    )
    assert result.json()["candidates"] == 1
    state = c.get("/api/state").json()
    assert state["briefing"]["review"] == 0
    task = state["tasks"][0]
    assert task["due_date"] == "2026-11-04" and task["due_at"] is None
    assert "DTSTART;VALUE=DATE:20261104" in c.get("/api/calendar.ics").text
    assert (
        asyncio.run(
            extract_ai(
                "Interview invitation\nPlease complete it soon.", "Gmail", "gmail"
            )
        )
        == []
    )
