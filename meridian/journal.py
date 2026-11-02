"""Recorded completion history, reusable check-ins, and weekly reflection.

Completion events preserve title/category/effort at the time of the action.
Rearming a reminder keeps history; undoing a completion invalidates that event.
"""

from datetime import date, datetime, timedelta
from fastapi import HTTPException
from .extract import TZ
from .store import stamp


def initialize(db):
    db.executescript(
        """
    CREATE TABLE IF NOT EXISTS reminders (
      id INTEGER PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL, minutes INTEGER NOT NULL, due_at TEXT,
      completed_at TEXT, cycle INTEGER NOT NULL DEFAULT 0,
      archived INTEGER NOT NULL DEFAULT 0, demo INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS activity (
      id INTEGER PRIMARY KEY, kind TEXT NOT NULL, entity_id INTEGER NOT NULL,
      cycle INTEGER NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL,
      minutes INTEGER NOT NULL, completed_at TEXT NOT NULL,
      demo INTEGER NOT NULL, voided INTEGER NOT NULL DEFAULT 0);
    CREATE UNIQUE INDEX IF NOT EXISTS activity_once
      ON activity(kind,entity_id,cycle,demo) WHERE voided=0;
    CREATE TABLE IF NOT EXISTS weekly_notes (
      week_start TEXT NOT NULL, demo INTEGER NOT NULL, wins TEXT NOT NULL DEFAULT '',
      friction TEXT NOT NULL DEFAULT '', next_focus TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
      PRIMARY KEY(week_start,demo));
    """
    )


def record_task(db, task_id, completed, at=None):
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return
    if completed:
        db.execute(
            """INSERT OR IGNORE INTO activity(kind,entity_id,cycle,title,category,minutes,completed_at,demo,notebook_category)
          VALUES('task',?,0,?,?,?,?,?,?)""",
            (
                task_id,
                row["title"],
                row["category"],
                row["minutes"],
                at or stamp(),
                row["demo"],
                row["notebook_category"],
            ),
        )
    else:
        db.execute(
            "UPDATE activity SET voided=1 WHERE kind='task' AND entity_id=? AND voided=0",
            (task_id,),
        )


def reminders(store, demo=False):
    with store.db() as db:
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM reminders WHERE demo=? ORDER BY archived,completed_at IS NOT NULL,due_at IS NULL,due_at,id",
                (demo,),
            )
        ]
        for row in rows:
            row["completions"] = db.execute(
                "SELECT count(*) FROM activity WHERE kind='reminder' AND entity_id=? AND voided=0",
                (row["id"],),
            ).fetchone()[0]
        return rows


def seed_reminders(store):
    with store.db() as db:
        # Never repopulate a user's reminder list. Only the example workspace is seeded once.
        if db.execute("SELECT 1 FROM reminders WHERE demo=1 LIMIT 1").fetchone():
            return
        now = datetime.now(TZ)
        examples = [
            (
                "Apply to a few good-fit roles",
                "Choose quality over volume. Check role fit, then record the applications.",
                "career",
                30,
            ),
            (
                "Follow up with recruiters",
                "Check recent conversations and send a thoughtful follow-up when appropriate.",
                "career",
                15,
            ),
            (
                "Check this week’s course updates",
                "Review announcements and make sure your deadlines still match the source.",
                "academic",
                10,
            ),
        ]
        for index, (title, notes, category, minutes) in enumerate(examples):
            due = (now + timedelta(days=index)).replace(
                hour=17, minute=0, second=0, microsecond=0
            )
            db.execute(
                "INSERT INTO reminders(title,notes,category,minutes,due_at,demo,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
                (title, notes, category, minutes, due.isoformat(), stamp(), stamp()),
            )


def get_reminder(db, reminder_id, demo):
    row = db.execute(
        "SELECT * FROM reminders WHERE id=? AND demo=?", (reminder_id, demo)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Reminder not found in this workspace")
    return row


def act(store, reminder_id, action, demo=False):
    with store.db() as db:
        row = get_reminder(db, reminder_id, demo)
        if action == "archive":
            db.execute(
                "UPDATE reminders SET archived=1,updated_at=? WHERE id=?",
                (stamp(), reminder_id),
            )
        elif action == "restore":
            db.execute(
                "UPDATE reminders SET archived=0,updated_at=? WHERE id=?",
                (stamp(), reminder_id),
            )
        elif row["archived"]:
            raise HTTPException(409, "Restore this reminder before using it")
        elif action == "complete":
            if not row["completed_at"]:
                at = stamp()
                db.execute(
                    "UPDATE reminders SET completed_at=?,updated_at=? WHERE id=?",
                    (at, at, reminder_id),
                )
                db.execute(
                    """INSERT INTO activity(kind,entity_id,cycle,title,category,minutes,completed_at,demo)
                  VALUES('reminder',?,?,?,?,?,?,?)""",
                    (
                        reminder_id,
                        row["cycle"],
                        row["title"],
                        row["category"],
                        row["minutes"],
                        at,
                        demo,
                    ),
                )
        elif action == "rearm":
            if row["completed_at"]:
                db.execute(
                    "UPDATE reminders SET completed_at=NULL,cycle=cycle+1,due_at=NULL,updated_at=? WHERE id=?",
                    (stamp(), reminder_id),
                )
        elif action == "undo":
            if row["completed_at"]:
                db.execute(
                    "UPDATE activity SET voided=1 WHERE kind='reminder' AND entity_id=? AND cycle=?",
                    (reminder_id, row["cycle"]),
                )
                db.execute(
                    "UPDATE reminders SET completed_at=NULL,updated_at=? WHERE id=?",
                    (stamp(), reminder_id),
                )
    return {"ok": True}


def monday(day):
    return day - timedelta(days=day.weekday())


def event_day(event):
    if event.get("date_only"):
        return date.fromisoformat(event["completed_at"][:10])
    value = datetime.fromisoformat(event["completed_at"])
    return (value if value.tzinfo else value.replace(tzinfo=TZ)).astimezone(TZ).date()


def review(store, week=None, demo=False, now=None):
    now = now or datetime.now(TZ)
    start = monday(week or now.date())
    end = start + timedelta(days=7)
    with store.db() as db:
        # Compare instants in application timezone, never ISO strings with mixed offsets.
        events = [
            dict(r)
            for r in db.execute(
                "SELECT a.* FROM activity a LEFT JOIN tasks t ON a.kind='task' AND t.id=a.entity_id WHERE a.demo=? AND a.voided=0 AND (a.kind!='task' OR t.deleted_at IS NULL) ORDER BY a.completed_at DESC",
                (demo,),
            )
        ]
        notes = db.execute(
            "SELECT * FROM weekly_notes WHERE week_start=? AND demo=?",
            (start.isoformat(), demo),
        ).fetchone()
    events = [
        e for e in events if start <= event_day(e) < end and event_day(e) <= now.date()
    ]
    tasks = store.tasks(demo)
    unfinished = [
        t
        for t in tasks
        if not t["completed"]
        and t["confidence"] != "review"
        and (not t.get("available_on") or t["available_on"] <= now.date().isoformat())
    ]
    overdue = [
        t
        for t in unfinished
        if t["confidence"] != "review"
        and (
            (t["due_at"] and datetime.fromisoformat(t["due_at"]) < now)
            or (t.get("due_date") and t["due_date"] < now.date().isoformat())
        )
    ]
    upcoming = [
        t
        for t in unfinished
        if t["confidence"] != "review"
        and (
            (
                t["due_at"]
                and now
                <= datetime.fromisoformat(t["due_at"])
                <= now + timedelta(days=7)
            )
            or (
                t.get("due_date")
                and now.date().isoformat()
                <= t["due_date"]
                <= (now.date() + timedelta(days=7)).isoformat()
            )
        )
    ]
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        matches = [e for e in events if event_day(e) == day]
        days.append(
            {
                "date": day.isoformat(),
                "count": len(matches),
                "minutes": sum(e["minutes"] for e in matches),
                "future": day > now.date(),
                "today": day == now.date(),
            }
        )
    # A daily backlog uses real creation/completion dates. Unknown creation dates stay explicit.
    with store.db() as db:
        all_tasks = [
            dict(r) for r in db.execute("SELECT * FROM tasks WHERE demo=?", (demo,))
        ]
    for day in days:
        key = day["date"]
        known = [
            t
            for t in all_tasks
            if t["confidence"] != "review"
            and not t["unknown_created_at"]
            and t["created_at"][:10] <= key
            and (not t["deleted_at"] or t["deleted_at"][:10] > key)
            and (not t["available_on"] or t["available_on"] <= key)
        ]
        day["added"] = sum(t["created_at"][:10] == key for t in known)
        day["open"] = sum(
            not t["completed_at"] or t["completed_at"][:10] > key for t in known
        )
    categories = [
        {
            "category": c,
            "count": sum(e["category"] == c for e in events),
            "minutes": sum(e["minutes"] for e in events if e["category"] == c),
        }
        for c in ["academic", "career", "personal"]
    ]
    from .notebook import CATEGORIES

    notebook_categories = [
        {
            "category": c,
            "count": sum(e.get("notebook_category") == c for e in events),
            "minutes": sum(
                e["minutes"] for e in events if e.get("notebook_category") == c
            ),
        }
        for c in CATEGORIES
    ]
    return {
        "notebook_categories": notebook_categories,
        "review_count": sum(
            t["confidence"] == "review" and not t["completed"] for t in tasks
        ),
        "unknown_created": sum(bool(t["unknown_created_at"]) for t in all_tasks),
        "week_start": start.isoformat(),
        "week_end": (end - timedelta(days=1)).isoformat(),
        "now": now.isoformat(),
        "events": events,
        "days": days,
        "categories": categories,
        "totals": {
            "completed": len(events),
            "tasks": sum(e["kind"] == "task" for e in events),
            "checkins": sum(e["kind"] == "reminder" for e in events),
            "minutes": sum(e["minutes"] for e in events),
            "open": len(unfinished),
            "overdue": len(overdue),
        },
        "unfinished": unfinished,
        "overdue": overdue,
        "upcoming": upcoming,
        "notes": (
            dict(notes) if notes else {"wins": "", "friction": "", "next_focus": ""}
        ),
    }
