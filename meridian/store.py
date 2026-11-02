import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import Candidate


def stamp():
    return datetime.now(timezone.utc).isoformat()


def identity(title, course):
    return re.sub(r"[^a-z0-9]", "", f"{course}:{title}".lower())


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript(
                """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY, identity TEXT NOT NULL, title TEXT NOT NULL,
              course TEXT NOT NULL, category TEXT NOT NULL, due_at TEXT,
              confidence TEXT NOT NULL, minutes INTEGER NOT NULL,
              destination TEXT NOT NULL, completed INTEGER DEFAULT 0,
              demo INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(identity, demo));
            CREATE TABLE IF NOT EXISTS evidence (
              id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id),
              source_id TEXT, source_type TEXT, source_url TEXT, quote TEXT,
              due_at TEXT, fingerprint TEXT, observed_at TEXT,
              UNIQUE(task_id, source_id, fingerprint));
            CREATE TABLE IF NOT EXISTS changes (
              id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id),
              message TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS blocks (
              id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id),
              title TEXT, start TEXT, end TEXT, kind TEXT, demo INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS syncs (
              source TEXT PRIMARY KEY, status TEXT, detail TEXT, synced_at TEXT);
            CREATE TABLE IF NOT EXISTS gmail_checkpoint (
              account TEXT NOT NULL, message_id TEXT NOT NULL, mode TEXT NOT NULL,
              processed_at TEXT NOT NULL, PRIMARY KEY(account,message_id,mode));
            CREATE TABLE IF NOT EXISTS gmail_progress (
              account TEXT PRIMARY KEY, query TEXT NOT NULL, processed INTEGER DEFAULT 0,
              cached INTEGER DEFAULT 0, state TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
            )

        from .journal import initialize

        with self.db() as db:
            initialize(db)
            from .notebook import initialize as notebook_initialize

            notebook_initialize(db)
            if "mode" not in {
                r[1] for r in db.execute("PRAGMA table_info(gmail_progress)")
            }:
                db.execute(
                    "ALTER TABLE gmail_progress ADD COLUMN mode TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def gmail_known(self, account, mode):
        with self.db() as db:
            return {
                r[0]
                for r in db.execute(
                    "SELECT message_id FROM gmail_checkpoint WHERE account=? AND mode=?",
                    (account, mode),
                )
            }

    def gmail_commit(self, account, message_id, mode, candidates):
        # Ingest is idempotent. A crash before the checkpoint safely replays this message.
        counts = self.ingest(candidates)
        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO gmail_checkpoint VALUES(?,?,?,?)",
                (account, message_id, mode, stamp()),
            )
        return counts

    def gmail_progress(
        self, account, query, processed=None, cached=None, state="running", mode=None
    ):
        with self.db() as db:
            old = db.execute(
                "SELECT processed,cached,mode FROM gmail_progress WHERE account=?",
                (account,),
            ).fetchone()
            db.execute(
                "INSERT OR REPLACE INTO gmail_progress(account,query,processed,cached,state,updated_at,mode) VALUES(?,?,?,?,?,?,?)",
                (
                    account,
                    query,
                    processed if processed is not None else (old[0] if old else 0),
                    cached if cached is not None else (old[1] if old else 0),
                    state,
                    stamp(),
                    mode if mode is not None else (old[2] if old else ""),
                ),
            )

    def ingest(self, candidates):
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        with self.db() as db:
            for candidate in candidates:
                c = (
                    candidate
                    if isinstance(candidate, Candidate)
                    else Candidate(**candidate)
                )
                due = c.due_at.isoformat() if c.due_at else None
                strict_gmail = c.source_type == "gmail" and c.source_id.endswith(
                    ":interview-deadline"
                )
                key = (
                    "gmail-interview:" + c.source_id
                    if strict_gmail
                    else identity(c.title, c.course)
                )
                day = c.due_date.isoformat() if c.due_date else None
                # Stable upstream IDs allow renames without creating duplicate obligations.
                row = (
                    db.execute(
                        """SELECT t.* FROM tasks t JOIN evidence e ON e.task_id=t.id
                  WHERE e.source_id=? AND t.demo=? AND t.course=? AND e.source_type='assignment' """,
                        (c.source_id, c.demo, c.course),
                    ).fetchone()
                    if c.source_type == "assignment"
                    else None
                )
                row = (
                    row
                    or db.execute(
                        "SELECT * FROM tasks WHERE identity=? AND demo=?", (key, c.demo)
                    ).fetchone()
                )
                if not row and c.source_type == "gmail" and not strict_gmail:
                    # Only exact, unique titles may link across course-less Gmail sources.
                    matches = [
                        r
                        for r in db.execute(
                            "SELECT * FROM tasks WHERE demo=?", (c.demo,)
                        )
                        if identity(r["title"], "") == identity(c.title, "")
                    ]
                    if len(matches) == 1:
                        row = matches[0]
                if not row:
                    cursor = db.execute(
                        """INSERT INTO tasks(identity,title,course,category,due_at,confidence,
                      minutes,destination,completed,demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            key,
                            c.title,
                            c.course,
                            c.category,
                            due,
                            c.confidence,
                            c.minutes,
                            c.destination,
                            int(
                                c.submitted
                                and c.destination == "Canvas"
                                and c.source_type == "assignment"
                            ),
                            c.demo,
                            stamp(),
                            stamp(),
                        ),
                    )
                    task_id = cursor.lastrowid
                    if day:
                        db.execute(
                            "UPDATE tasks SET due_date=? WHERE id=?", (day, task_id)
                        )
                    counts["created"] += 1
                else:
                    task_id = row["id"]
                fp = hashlib.sha256(
                    json.dumps([c.evidence, due, day, c.submitted, c.title]).encode()
                ).hexdigest()
                cursor = db.execute(
                    """INSERT OR IGNORE INTO evidence(task_id,source_id,source_type,
                  source_url,quote,due_at,fingerprint,observed_at) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        c.source_id,
                        c.source_type,
                        c.source_url,
                        c.evidence,
                        due,
                        fp,
                        stamp(),
                    ),
                )
                if row:
                    if not cursor.rowcount:
                        counts["unchanged"] += 1
                        continue
                    if due != row["due_at"] and (
                        due is not None or c.source_type == "assignment"
                    ):
                        # Only a known structured assignment can automatically replace its deadline.
                        prior = db.execute(
                            "SELECT 1 FROM evidence WHERE task_id=? AND source_id=? AND id!=?",
                            (task_id, c.source_id, cursor.lastrowid),
                        ).fetchone()
                        automatic = (
                            c.source_type == "assignment"
                            and prior
                            and (c.confidence == "confirmed" or due is None)
                        )
                        if automatic:
                            db.execute(
                                "UPDATE tasks SET due_at=?, confidence=?,updated_at=? WHERE id=?",
                                (
                                    due,
                                    "confirmed" if due else "review",
                                    stamp(),
                                    task_id,
                                ),
                            )
                            db.execute(
                                "DELETE FROM blocks WHERE task_id=? AND kind='work'",
                                (task_id,),
                            )
                            message = f"Canvas deadline changed: {row['due_at'] or 'unset'} → {due}. Work blocks cleared for replanning."
                        else:
                            db.execute(
                                "UPDATE tasks SET confidence='review',updated_at=? WHERE id=?",
                                (stamp(), task_id),
                            )
                            message = f"Conflicting deadline detected: {due}. Review evidence before changing the canonical deadline."
                        db.execute(
                            "INSERT INTO changes(task_id,message,created_at) VALUES(?,?,?)",
                            (task_id, message, stamp()),
                        )
                    if (
                        c.submitted
                        and c.destination == "Canvas"
                        and c.source_type == "assignment"
                    ):
                        db.execute(
                            "UPDATE tasks SET completed=1 WHERE id=?", (task_id,)
                        )
                        db.execute(
                            "DELETE FROM blocks WHERE task_id=? AND kind='work'",
                            (task_id,),
                        )
                    counts["updated"] += 1
                if (
                    c.submitted
                    and c.destination == "Canvas"
                    and c.source_type == "assignment"
                ):
                    from .journal import record_task

                    record_task(db, task_id, True)
        return counts

    def tasks(self, demo=False):
        with self.db() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM tasks WHERE demo=? AND deleted_at IS NULL ORDER BY completed,due_at IS NULL,due_at",
                    (demo,),
                )
            ]
            for row in rows:
                row["evidence"] = [
                    dict(e)
                    for e in db.execute(
                        "SELECT * FROM evidence WHERE task_id=? ORDER BY id DESC",
                        (row["id"],),
                    )
                ]
                row["changes"] = [
                    dict(e)
                    for e in db.execute(
                        "SELECT * FROM changes WHERE task_id=? ORDER BY id DESC",
                        (row["id"],),
                    )
                ]
            return rows

    def sync_status(self, source, status, detail):
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO syncs VALUES(?,?,?,?)",
                (source, status, detail, stamp()),
            )
