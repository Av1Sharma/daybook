from datetime import datetime, timedelta
import pytest
from meridian.models import Candidate
from meridian.store import Store
from meridian.extract import extract, plain, TZ
from meridian.planner import plan


def candidate(**kwargs):
    return Candidate(
        **(
            dict(
                title="Problem set 7",
                course="CS 2800",
                due_at="2026-11-02T23:59:00-05:00",
                confidence="confirmed",
                source_id="assignment:7",
                source_type="assignment",
                evidence="Problem set 7 due November 2",
            )
            | kwargs
        )
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def test_repeated_snapshot_is_idempotent(store):
    assert store.ingest([candidate()])["created"] == 1
    assert store.ingest([candidate()])["unchanged"] == 1
    assert len(store.tasks()) == 1
    assert len(store.tasks()[0]["evidence"]) == 1


def test_cross_source_dedup_preserves_conflict(store):
    store.ingest([candidate()])
    store.ingest(
        [
            candidate(
                source_id="gmail:9",
                source_type="gmail",
                due_at="2026-11-04T23:59:00-05:00",
                evidence="Extended to November 4",
            )
        ]
    )
    t = store.tasks()[0]
    assert t["confidence"] == "review"
    assert t["due_at"].startswith("2026-11-02")
    assert len(t["evidence"]) == 2
    assert "Conflicting" in t["changes"][0]["message"]


def test_assignment_change_invalidates_work_blocks(store):
    store.ingest([candidate()])
    tid = store.tasks()[0]["id"]
    with store.db() as db:
        db.execute(
            "INSERT INTO blocks(task_id,title,start,end,kind) VALUES(?,?,?,?,?)",
            (
                tid,
                "Work",
                "2026-11-01T10:00:00-05:00",
                "2026-11-01T11:00:00-05:00",
                "work",
            ),
        )
    store.ingest(
        [candidate(title="Problem set 7 revised", due_at="2026-11-05T23:59:00-05:00")]
    )
    assert len(store.tasks()) == 1
    assert store.tasks()[0]["due_at"].startswith("2026-11-05")
    assert store.tasks()[0]["confidence"] == "confirmed"
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM blocks").fetchone()[0] == 0


def test_gradescope_not_completed_from_canvas(store):
    store.ingest([candidate(destination="Gradescope", submitted=True)])
    assert not store.tasks()[0]["completed"]


def test_canvas_submission_can_complete(store):
    store.ingest([candidate(submitted=True)])
    assert store.tasks()[0]["completed"]


def test_demo_and_personal_isolation(store):
    store.ingest([candidate(), candidate(demo=True)])
    assert len(store.tasks()) == len(store.tasks(True)) == 1


def test_ambiguous_date_never_invented():
    items = extract("Quiz next week.\nHomework due 2026-11-03", "Math", "syllabus")
    assert len(items) == 2
    assert all(t.due_at is None and t.confidence == "review" for t in items)


def test_explicit_date_and_destination():
    t = extract("Problem set 7 due 2026-11-02 23:59 on Gradescope", "CS", "syllabus")[0]
    assert t.due_at.hour == 23 and t.due_at.minute == 59
    assert t.destination == "Gradescope"
    assert t.title == "Problem set 7"


def test_weekly_rule_bounded():
    items = extract(
        "Homework due every Friday at 11:59 PM on Gradescope",
        "CS",
        "syllabus",
        start="2026-10-26",
        end="2026-11-08",
    )
    assert len(items) == 2
    assert [t.due_at.day for t in items] == [30, 6]
    assert all(t.confidence == "expected" and t.due_at.hour == 23 for t in items)
    with pytest.raises(ValueError):
        extract(
            "Homework due every Friday at 11:59 PM",
            "CS",
            "syllabus",
            start="2026-01-01",
            end="2027-01-01",
        )


def test_acknowledgment_is_not_action():
    assert not extract(
        "Thank you for applying. Application received.", "Career", "gmail"
    )


def test_html_scripts_not_interpreted():
    assert (
        plain(
            "<p>Quiz tomorrow</p><script>Homework due 2026-11-03 12:00</script>"
        ).strip()
        == "Quiz tomorrow"
    )


def test_timezone_required():
    with pytest.raises(ValueError):
        candidate(due_at="2026-11-03T12:00:00")


def test_javascript_links_rejected():
    with pytest.raises(ValueError):
        candidate(source_url="javascript:alert(1)")


def test_plan_avoids_busy_review_and_late_work():
    now = datetime(2026, 10, 28, 8, tzinfo=TZ)
    tasks = [
        dict(
            id=1,
            title="Valid",
            minutes=60,
            due_at="2026-10-29T23:59:00-04:00",
            confidence="confirmed",
            completed=False,
            demo=False,
        ),
        dict(
            id=2,
            title="Uncertain",
            minutes=30,
            due_at=None,
            confidence="review",
            completed=False,
            demo=False,
        ),
        dict(
            id=3,
            title="Too late",
            minutes=600,
            due_at="2026-10-28T10:00:00-04:00",
            confidence="confirmed",
            completed=False,
            demo=False,
        ),
    ]
    blocks = [
        dict(
            task_id=None,
            kind="busy",
            start="2026-10-28T09:00:00-04:00",
            end="2026-10-28T11:00:00-04:00",
        )
    ]
    suggestions = plan(tasks, blocks, now)
    assert len(suggestions) == 1 and suggestions[0]["task_id"] == 1
    assert datetime.fromisoformat(suggestions[0]["start"]).hour == 11


def test_plan_does_not_duplicate_existing():
    now = datetime(2026, 10, 28, 8, tzinfo=TZ)
    task = dict(
        id=1,
        title="Valid",
        minutes=60,
        due_at="2026-10-29T23:59:00-04:00",
        confidence="confirmed",
        completed=False,
        demo=False,
    )
    block = dict(
        task_id=1,
        kind="work",
        start="2026-10-28T09:00:00-04:00",
        end="2026-10-28T10:00:00-04:00",
    )
    assert plan([task], [block], now) == []


def test_removed_canvas_deadline_cannot_leave_stale_date(store):
    store.ingest([candidate()])
    store.ingest(
        [candidate(due_at=None, confidence="review", evidence="Deadline removed")]
    )
    t = store.tasks()[0]
    assert t["due_at"] is None and t["confidence"] == "review"
    assert len(t["changes"]) == 1


def test_unique_gmail_title_links_across_course_context(store):
    store.ingest([candidate()])
    store.ingest(
        [
            candidate(
                course="Gmail",
                source_type="gmail",
                source_id="gmail:7",
                due_at="2026-11-04T23:59:00-05:00",
            )
        ]
    )
    tasks = store.tasks()
    assert len(tasks) == 1
    assert tasks[0]["course"] == "CS 2800" and tasks[0]["confidence"] == "review"
    assert len(tasks[0]["evidence"]) == 2


def test_ambiguous_same_title_does_not_cross_link(store):
    store.ingest([candidate(), candidate(course="Math")])
    store.ingest([candidate(course="Gmail", source_type="gmail", source_id="gmail:7")])
    assert len(store.tasks()) == 3
