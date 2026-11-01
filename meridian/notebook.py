"""DayBook-compatible notebook records, lossless migration, and local backups."""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from .store import stamp
from .extract import TZ

CATEGORIES = [
    "Academics / classes",
    "LeetCode / coding",
    "Internships / jobs",
    "Projects",
    "Personal",
]


def initialize(db):
    columns = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
    additions = {
        "notebook_id": "TEXT",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "notebook_category": "TEXT NOT NULL DEFAULT ''",
        "due_date": "TEXT",
        "importance": "INTEGER NOT NULL DEFAULT 2",
        "repeat_rule": "TEXT NOT NULL DEFAULT 'none'",
        "available_on": "TEXT",
        "completed_at": "TEXT",
        "deleted_at": "TEXT",
        "parent_id": "INTEGER",
        "unknown_created_at": "INTEGER NOT NULL DEFAULT 0",
        "date_only_completion": "INTEGER NOT NULL DEFAULT 0",
        "calendar_event_id": "INTEGER",
    }
    for name, kind in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {kind}")
    activity = {r[1] for r in db.execute("PRAGMA table_info(activity)")}
    if "date_only" not in activity:
        db.execute(
            "ALTER TABLE activity ADD COLUMN date_only INTEGER NOT NULL DEFAULT 0"
        )
    if "notebook_category" not in activity:
        db.execute(
            "ALTER TABLE activity ADD COLUMN notebook_category TEXT NOT NULL DEFAULT ''"
        )
    db.executescript(
        """
      CREATE UNIQUE INDEX IF NOT EXISTS notebook_task_id ON tasks(notebook_id) WHERE notebook_id IS NOT NULL;
      CREATE TABLE IF NOT EXISTS reference_notes (
        id INTEGER PRIMARY KEY, source_id TEXT UNIQUE, title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', items TEXT NOT NULL DEFAULT '[]',
        scope TEXT NOT NULL DEFAULT 'general', archived INTEGER NOT NULL DEFAULT 0,
        demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS calendar_events (
        id INTEGER PRIMARY KEY, source_id TEXT UNIQUE, course TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL, date TEXT NOT NULL, end_date TEXT, time TEXT, end_time TEXT,
        notes TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
        tentative INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'deadline',
        source TEXT NOT NULL DEFAULT '', linked_task_id INTEGER,
        demo INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS calendar_cadences (
        id INTEGER PRIMARY KEY, source_id TEXT UNIQUE, data TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS daybook_records (
        source_id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, entity_id INTEGER);
      CREATE TABLE IF NOT EXISTS notebook_imports (
        digest TEXT PRIMARY KEY, imported_at TEXT NOT NULL, summary TEXT NOT NULL);
    """
    )


def broad_category(value):
    return (
        "career"
        if value == "Internships / jobs"
        else "academic" if value in CATEGORIES[:2] else "personal"
    )


def valid_day(value):
    if not value:
        return None
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Choose a valid calendar date")
    return value


def add_task(store, data, demo=False):
    now = stamp()
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 300:
        raise ValueError("Use a task name from 1 to 300 characters")
    category = data.get("notebook_category", "Personal")
    if category not in CATEGORIES:
        raise ValueError("Choose a notebook category")
    repeat = data.get("repeat_rule", "none")
    if repeat not in ("none", "daily", "weekly"):
        raise ValueError("Choose a repeat schedule")
    due = valid_day(data.get("due_date"))
    due_at_value = data.get("due_at")
    if due_at_value:
        value = (
            due_at_value
            if isinstance(due_at_value, datetime)
            else datetime.fromisoformat(due_at_value)
        )
        due = value.astimezone(TZ).date().isoformat()
    if repeat != "none" and not due:
        due = datetime.now(TZ).date().isoformat()
    importance = int(data.get("importance", 2))
    minutes = int(data.get("minutes") or 0)
    if importance not in (1, 2, 3) or not 0 <= minutes <= 1440:
        raise ValueError("Use importance 1–3 and effort 0–1440 minutes")
    due_at = data.get("due_at")
    if isinstance(due_at, datetime):
        due_at = due_at.isoformat()
    with store.db() as db:
        cursor = db.execute(
            """INSERT INTO tasks(identity,title,course,category,confidence,minutes,destination,
          completed,demo,created_at,updated_at,notebook_id,notes,notebook_category,due_date,importance,repeat_rule,available_on)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "notebook:" + uuid.uuid4().hex,
                title,
                data.get("course") or category,
                broad_category(category),
                "confirmed",
                minutes,
                "Notebook",
                0,
                demo,
                now,
                now,
                uuid.uuid4().hex,
                str(data.get("notes", ""))[:20000],
                category,
                due,
                importance,
                repeat,
                due if repeat != "none" else None,
            ),
        )
        if due_at:
            db.execute(
                "UPDATE tasks SET due_at=?,due_date=NULL WHERE id=?",
                (due_at, cursor.lastrowid),
            )
        return cursor.lastrowid


def complete_task(db, task, completed, at=None):
    now = at or stamp()
    today = datetime.fromisoformat(now).astimezone(TZ).date().isoformat()
    if completed:
        if task["available_on"] and task["available_on"] > today:
            raise ValueError("This recurring task is scheduled for a later day")
        if not task["completed"] and task["repeat_rule"] != "none":
            next_day = (
                date.fromisoformat(today)
                + timedelta(days=1 if task["repeat_rule"] == "daily" else 7)
            ).isoformat()
            existing = db.execute(
                "SELECT 1 FROM tasks WHERE parent_id=? AND deleted_at IS NULL",
                (task["id"],),
            ).fetchone()
            if not existing:
                names = [
                    r[1] for r in db.execute("PRAGMA table_info(tasks)") if r[1] != "id"
                ]
                values = dict(task)
                values.update(
                    identity="notebook:" + uuid.uuid4().hex,
                    notebook_id=uuid.uuid4().hex,
                    completed=0,
                    completed_at=None,
                    due_at=None,
                    due_date=next_day,
                    available_on=next_day,
                    parent_id=task["id"],
                    created_at=now,
                    updated_at=now,
                    unknown_created_at=0,
                    date_only_completion=0,
                    calendar_event_id=None,
                )
                db.execute(
                    f"INSERT INTO tasks({','.join(names)}) VALUES({','.join('?' for _ in names)})",
                    [values[n] for n in names],
                )
        db.execute(
            "UPDATE tasks SET completed_at=?,date_only_completion=0 WHERE id=?",
            (now, task["id"]),
        )
    else:
        child = db.execute(
            "SELECT * FROM tasks WHERE parent_id=? AND deleted_at IS NULL",
            (task["id"],),
        ).fetchone()
        if child and child["completed"]:
            raise ValueError("Reopen the most recent recurring occurrence first")
        if child:
            db.execute("UPDATE tasks SET deleted_at=? WHERE id=?", (now, child["id"]))
        db.execute("UPDATE tasks SET completed_at=NULL WHERE id=?", (task["id"],))


def notes(store, demo=False, archived=False):
    with store.db() as db:
        return [
            {**dict(r), "items": json.loads(r["items"])}
            for r in db.execute(
                "SELECT * FROM reference_notes WHERE demo=? AND archived=? ORDER BY updated_at DESC,id",
                (demo, archived),
            )
        ]


def events(store, demo=False):
    with store.db() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM calendar_events WHERE demo=? AND archived=0 ORDER BY date,time,id",
                (demo,),
            )
        ]


def history(store, demo=False):
    with store.db() as db:
        return [
            dict(r)
            for r in db.execute(
                """SELECT a.*,t.deleted_at FROM activity a
          LEFT JOIN tasks t ON a.kind='task' AND t.id=a.entity_id
          WHERE a.demo=? AND a.voided=0 AND (a.kind!='task' OR t.deleted_at IS NULL)
          ORDER BY a.completed_at DESC,a.id DESC""",
                (demo,),
            )
        ]


def backup(store, label="meridian"):
    folder = Path(store.path).parent / "Backups"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = (
        folder
        / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.db"
    )
    source = sqlite3.connect(store.path)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    target.chmod(0o600)
    return target


def export_notebook(store):
    with store.db() as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            "kind": "meridian-backup",
            "version": 1,
            "exported_at": stamp(),
            "tables": {
                name: [dict(r) for r in db.execute(f'SELECT * FROM "{name}"')]
                for name in tables
            },
        }


def restore_notebook(store, payload):
    if not isinstance(payload, dict):
        raise ValueError("Choose a notebook backup object")
    current = export_notebook(store)
    if (
        payload.get("kind") != "meridian-backup"
        or payload.get("version") != 1
        or set(payload.get("tables", {})) != set(current["tables"])
    ):
        raise ValueError("This is not a compatible Meridian notebook backup")
    with store.db() as db:
        for name, rows in payload["tables"].items():
            if name == "gmail_progress" and isinstance(rows, list):
                rows = [
                    (
                        {**row, "mode": row.get("mode", "")}
                        if isinstance(row, dict)
                        else row
                    )
                    for row in rows
                ]
                payload["tables"][name] = rows
            columns = {r[1] for r in db.execute(f'PRAGMA table_info("{name}")')}
            if not isinstance(rows, list) or any(
                not isinstance(r, dict) or set(r) != columns for r in rows
            ):
                raise ValueError("Backup records do not match the notebook schema")
    saved = backup(store, "before-restore")
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("PRAGMA defer_foreign_keys=ON")
        for name in payload["tables"]:
            db.execute(f'DELETE FROM "{name}"')
        for name, rows in payload["tables"].items():
            for row in rows:
                db.execute(
                    f'INSERT INTO "{name}"({",".join(row)}) VALUES({",".join("?" for _ in row)})',
                    list(row.values()),
                )
    return saved


def import_daybook(store, payload):
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or not isinstance(payload.get("tasks"), list)
    ):
        raise ValueError("Choose a version 1 DayBook notebook or backup")
    if any(
        not isinstance(t, dict)
        or not isinstance(t.get("id"), str)
        or not isinstance(t.get("title"), str)
        for t in payload["tasks"]
    ):
        raise ValueError("DayBook contains an invalid task")
    # Preserve every original field, including unknown dates and migration provenance.
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with store.db() as db:
        previous = db.execute(
            "SELECT summary FROM notebook_imports WHERE digest=?", (digest,)
        ).fetchone()
        if previous:
            return {**json.loads(previous[0]), "already_imported": True}
    backup(store, "before-daybook-merge")
    folder = Path(store.path).parent / "Backups"
    original = folder / f"Daybook-original-{digest[:12]}.json"
    if not original.exists():
        fd = os.open(original, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(raw)
    counts = {
        "tasks": 0,
        "completions": 0,
        "reminders": 0,
        "notes": 0,
        "events": 0,
        "cadences": 0,
        "deleted": 0,
    }
    now = stamp()
    mapping = {}
    from .journal import record_task

    with store.db() as db:
        # Reference collections have no required IDs in DayBook; index+title is stable across repeat imports.
        references = [
            ("reference:" + str(i) + ":" + str(n.get("title", "")), n)
            for i, n in enumerate(payload.get("references", []))
        ]
        for task in payload["tasks"]:
            source = "daybook:task:" + task["id"]
            existing = db.execute(
                "SELECT entity_id,kind FROM daybook_records WHERE source_id=?",
                (source,),
            ).fetchone()
            if existing:
                if existing["kind"] == "task":
                    mapping[task["id"]] = existing[0]
                continue
            if task.get("recordType") == "reference":
                references.append(
                    (
                        "task-reference:" + task["id"],
                        {
                            "title": task["title"],
                            "description": task.get("sourceHint", ""),
                            "items": [],
                            "scope": (
                                "internships"
                                if task.get("category") == "Internships / jobs"
                                else "general"
                            ),
                        },
                    )
                )
                continue
            category = task.get("category", "Personal")
            due = valid_day(task.get("due"))
            deleted = task.get("deletedAt")
            completion = task.get("completedAt")
            minutes = int(task.get("effort") or 0)
            if task.get("surface") == "internships" or task.get("reminderId"):
                cursor = db.execute(
                    """INSERT INTO reminders(title,notes,category,minutes,due_at,completed_at,archived,demo,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task["title"],
                        task.get("sourceHint", ""),
                        "career",
                        minutes,
                        None,
                        completion,
                        bool(deleted),
                        0,
                        task.get("createdAt") or now,
                        now,
                    ),
                )
                entity_id = cursor.lastrowid
                if completion and not deleted:
                    db.execute(
                        """INSERT INTO activity(kind,entity_id,cycle,title,category,minutes,completed_at,demo,date_only)
                      VALUES('reminder',?,0,?,'career',?,?,0,?)""",
                        (
                            entity_id,
                            task["title"],
                            minutes,
                            completion,
                            bool(task.get("dateOnlyCompletion")),
                        ),
                    )
                    counts["completions"] += 1
                counts["reminders"] += 1
                kind = "reminder"
            else:
                cursor = db.execute(
                    """INSERT INTO tasks(identity,title,course,category,confidence,minutes,destination,completed,demo,created_at,updated_at,
                  notebook_id,notes,notebook_category,due_date,importance,repeat_rule,available_on,completed_at,deleted_at,unknown_created_at,date_only_completion)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        source,
                        task["title"],
                        category,
                        broad_category(category),
                        "confirmed",
                        minutes,
                        "Notebook",
                        bool(completion),
                        0,
                        task.get("createdAt") or now,
                        now,
                        task["id"],
                        task.get("sourceHint", ""),
                        category,
                        due,
                        int(task.get("importance", 2)),
                        task.get("repeat", "none"),
                        valid_day(task.get("available")),
                        completion,
                        deleted,
                        bool(task.get("unknownCreatedAt")),
                        bool(task.get("dateOnlyCompletion")),
                    ),
                )
                entity_id = cursor.lastrowid
                mapping[task["id"]] = entity_id
                db.execute(
                    """INSERT INTO evidence(task_id,source_id,source_type,source_url,quote,fingerprint,observed_at)
                  VALUES(?,?,'manual','',?,?,?)""",
                    (
                        entity_id,
                        source,
                        "Imported from DayBook. " + task.get("sourceHint", ""),
                        digest + ":" + task["id"],
                        now,
                    ),
                )
                if completion and not deleted:
                    record_task(db, entity_id, True, completion)
                    db.execute(
                        "UPDATE activity SET date_only=? WHERE kind='task' AND entity_id=?",
                        (bool(task.get("dateOnlyCompletion")), entity_id),
                    )
                    counts["completions"] += 1
                counts["tasks"] += 1
                counts["deleted"] += bool(deleted)
                kind = "task"
            db.execute(
                "INSERT INTO daybook_records VALUES(?,?,?,?)",
                (source, kind, json.dumps(task), entity_id),
            )
        for task in payload["tasks"]:
            if (
                task.get("parentId")
                and task["id"] in mapping
                and task["parentId"] in mapping
            ):
                db.execute(
                    "UPDATE tasks SET parent_id=? WHERE id=?",
                    (mapping[task["parentId"]], mapping[task["id"]]),
                )
        for sid, note in references:
            source = "daybook:" + sid
            if db.execute(
                "SELECT 1 FROM daybook_records WHERE source_id=?", (source,)
            ).fetchone():
                continue
            cursor = db.execute(
                """INSERT INTO reference_notes(source_id,title,description,items,scope,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?)""",
                (
                    source,
                    note.get("title", "Reference"),
                    note.get("description", ""),
                    json.dumps(note.get("items", [])),
                    note.get("scope", "general"),
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO daybook_records VALUES(?,?,?,?)",
                (source, "reference", json.dumps(note), cursor.lastrowid),
            )
            counts["notes"] += 1
        for event in payload.get("calendarEvents", []):
            source = "daybook:event:" + event["id"]
            if db.execute(
                "SELECT 1 FROM daybook_records WHERE source_id=?", (source,)
            ).fetchone():
                continue
            cursor = db.execute(
                """INSERT INTO calendar_events(source_id,course,title,date,end_date,time,end_time,notes,location,tentative,kind,source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source,
                    event.get("course", ""),
                    event["title"],
                    valid_day(event["date"]),
                    valid_day(event.get("endDate")),
                    event.get("time"),
                    event.get("endTime"),
                    event.get("notes", ""),
                    event.get("location", ""),
                    bool(event.get("tentative")),
                    event.get("kind", "deadline"),
                    event.get("source", "DayBook"),
                ),
            )
            event_id = cursor.lastrowid
            linked = next(
                (
                    t
                    for t in payload["tasks"]
                    if t.get("calendarEventId") == event["id"] and t["id"] in mapping
                ),
                None,
            )
            if linked:
                db.execute(
                    "UPDATE calendar_events SET linked_task_id=? WHERE id=?",
                    (mapping[linked["id"]], event_id),
                )
                db.execute(
                    "UPDATE tasks SET calendar_event_id=? WHERE id=?",
                    (event_id, mapping[linked["id"]]),
                )
            db.execute(
                "INSERT INTO daybook_records VALUES(?,?,?,?)",
                (source, "event", json.dumps(event), event_id),
            )
            counts["events"] += 1
        for i, cadence in enumerate(payload.get("calendarCadences", [])):
            source = "daybook:cadence:" + str(cadence.get("id", i))
            cursor = db.execute(
                "INSERT OR IGNORE INTO calendar_cadences(source_id,data) VALUES(?,?)",
                (source, json.dumps(cadence)),
            )
            counts["cadences"] += cursor.rowcount
        db.execute(
            "INSERT OR IGNORE INTO daybook_records VALUES(?,?,?,NULL)",
            ("daybook:root:" + digest, "root", raw),
        )
        db.execute(
            "INSERT INTO notebook_imports VALUES(?,?,?)",
            (digest, now, json.dumps(counts)),
        )
    return counts
