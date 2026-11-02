import json
import sqlite3
import threading
import uuid
from datetime import datetime, time
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from . import notebook
from .models import NotebookTask, ReferenceNote, CalendarEvent, CalendarCadence
from .store import stamp
from .extract import TZ


def attach(app, store):
    tracking_lock = threading.Lock()

    def record(table, identifier):
        with store.db() as db:
            row = db.execute(
                f"SELECT * FROM {table} WHERE id=?", (identifier,)
            ).fetchone()
        if not row:
            raise HTTPException(404, "That record is no longer available")
        return dict(row)

    @app.get("/api/notebook")
    def state(demo: bool = False):
        with store.db() as db:
            trash = [
                dict(r)
                for r in db.execute(
                    "SELECT id,title,deleted_at,notebook_category FROM tasks WHERE demo=? AND deleted_at IS NOT NULL AND NOT EXISTS(SELECT 1 FROM changes c WHERE c.task_id=tasks.id AND c.message='Excluded by interview-only email policy. Recoverable from Trash.') ORDER BY deleted_at DESC",
                    (demo,),
                )
            ]
            cadences = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM calendar_cadences WHERE demo=?", (demo,)
                )
            ]
        return {
            "notes": notebook.notes(store, demo),
            "archived_notes": notebook.notes(store, demo, True),
            "events": notebook.events(store, demo),
            "cadences": cadences,
            "history": notebook.history(store, demo),
            "trash": trash,
            "categories": notebook.CATEGORIES,
        }

    @app.post("/api/notebook/tasks")
    def add(data: NotebookTask):
        try:
            return {"id": notebook.add_task(store, data.model_dump(), data.demo)}
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.put("/api/notebook/tasks/{identifier}")
    def edit(identifier: int, data: NotebookTask):
        record("tasks", identifier)
        try:
            due = notebook.valid_day(data.due_date)
            if data.due_at:
                due = data.due_at.astimezone(TZ).date().isoformat()
        except ValueError as error:
            raise HTTPException(422, str(error))
        if data.repeat_rule != "none" and not due:
            due = datetime.now(TZ).date().isoformat()
        if not data.title.strip():
            raise HTTPException(422, "Give your task a name")
        with store.db() as db:
            db.execute(
                """UPDATE tasks SET title=?,notes=?,notebook_category=?,category=?,course=?,due_date=?,due_at=?,
              importance=?,repeat_rule=?,available_on=?,minutes=?,updated_at=? WHERE id=?""",
                (
                    data.title.strip(),
                    data.notes,
                    data.notebook_category,
                    notebook.broad_category(data.notebook_category),
                    data.course or data.notebook_category,
                    None if data.due_at else due,
                    data.due_at.isoformat() if data.due_at else None,
                    data.importance,
                    data.repeat_rule,
                    due if data.repeat_rule != "none" else None,
                    data.minutes,
                    stamp(),
                    identifier,
                ),
            )
            db.execute(
                "DELETE FROM blocks WHERE task_id=? AND kind='work'", (identifier,)
            )
            db.execute(
                "INSERT INTO changes(task_id,message,created_at) VALUES(?,?,?)",
                (
                    identifier,
                    "Notebook task edited. Original evidence preserved.",
                    stamp(),
                ),
            )
        return {"ok": True}

    @app.delete("/api/notebook/tasks/{identifier}")
    def trash(identifier: int):
        record("tasks", identifier)
        with store.db() as db:
            db.execute(
                "UPDATE tasks SET deleted_at=? WHERE id=?", (stamp(), identifier)
            )
            db.execute(
                "DELETE FROM blocks WHERE task_id=? AND kind='work'", (identifier,)
            )
        return {"ok": True}

    @app.post("/api/notebook/tasks/{identifier}/restore")
    def restore_task(identifier: int):
        record("tasks", identifier)
        with store.db() as db:
            db.execute("UPDATE tasks SET deleted_at=NULL WHERE id=?", (identifier,))
        return {"ok": True}

    @app.post("/api/reference-notes")
    def add_note(data: ReferenceNote):
        with store.db() as db:
            cursor = db.execute(
                "INSERT INTO reference_notes(title,description,items,scope,demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (
                    data.title,
                    data.description,
                    json.dumps(data.items),
                    data.scope,
                    data.demo,
                    stamp(),
                    stamp(),
                ),
            )
        return {"id": cursor.lastrowid}

    @app.put("/api/reference-notes/{identifier}")
    def edit_note(identifier: int, data: ReferenceNote):
        record("reference_notes", identifier)
        with store.db() as db:
            db.execute(
                "UPDATE reference_notes SET title=?,description=?,items=?,scope=?,archived=?,updated_at=? WHERE id=?",
                (
                    data.title,
                    data.description,
                    json.dumps(data.items),
                    data.scope,
                    data.archived,
                    stamp(),
                    identifier,
                ),
            )
        return {"ok": True}

    def event_values(data):
        try:
            if not notebook.valid_day(data.date):
                raise ValueError("Choose an event date")
            notebook.valid_day(data.end_date)
            if data.end_date and data.end_date < data.date:
                raise ValueError("End date must follow the start date")
            if data.time:
                time.fromisoformat(data.time)
            if data.end_time:
                time.fromisoformat(data.end_time)
                if not data.time:
                    raise ValueError("Choose a start time before an end time")
                if (
                    not data.end_date or data.end_date == data.date
                ) and data.end_time <= data.time:
                    raise ValueError("End time must follow start time")
        except ValueError as error:
            raise HTTPException(422, str(error))
        return data.model_dump()

    @app.post("/api/calendar-events")
    def add_event(data: CalendarEvent):
        values = event_values(data)
        with store.db() as db:
            cursor = db.execute(
                f"INSERT INTO calendar_events({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                list(values.values()),
            )
        return {"id": cursor.lastrowid}

    @app.put("/api/calendar-events/{identifier}")
    def edit_event(identifier: int, data: CalendarEvent):
        record("calendar_events", identifier)
        values = event_values(data)
        with store.db() as db:
            db.execute(
                f"UPDATE calendar_events SET {','.join(key+'=?' for key in values)} WHERE id=?",
                [*values.values(), identifier],
            )
        return {"ok": True}

    @app.delete("/api/calendar-events/{identifier}")
    def remove_event(identifier: int):
        record("calendar_events", identifier)
        with store.db() as db:
            db.execute(
                "UPDATE calendar_events SET archived=1 WHERE id=?", (identifier,)
            )
        return {"ok": True}

    @app.post("/api/calendar-events/{identifier}/track")
    def track(identifier: int):
        with tracking_lock:
            event = record("calendar_events", identifier)
            if (
                event["archived"]
                or event["tentative"]
                or (event["end_date"] and event["end_date"] != event["date"])
                or event["kind"] in ("break", "cadence", "activity")
            ):
                raise HTTPException(
                    422, "Only a confirmed single-date event can create a deadline task"
                )
            if event["linked_task_id"]:
                return {"id": event["linked_task_id"], "existing": True}
            identifier_task = notebook.add_task(
                store,
                {
                    "title": event["title"],
                    "course": event["course"],
                    "notebook_category": "Academics / classes",
                    "due_date": event["date"],
                    "notes": event["notes"],
                },
                event["demo"],
            )
            with store.db() as db:
                due = (
                    datetime.combine(
                        datetime.fromisoformat(event["date"]).date(),
                        time.fromisoformat(event["time"]),
                        TZ,
                    ).isoformat()
                    if event["time"]
                    else None
                )
                db.execute(
                    "UPDATE tasks SET calendar_event_id=?,due_at=?,due_date=? WHERE id=?",
                    (identifier, due, None if due else event["date"], identifier_task),
                )
                db.execute(
                    "UPDATE calendar_events SET linked_task_id=? WHERE id=?",
                    (identifier_task, identifier),
                )
            return {"id": identifier_task}

    @app.post("/api/calendar-cadences")
    def add_cadence(data: CalendarCadence):
        try:
            if not notebook.valid_day(data.start) or not notebook.valid_day(data.end):
                raise ValueError("Choose a start and end date")
            if data.end < data.start:
                raise ValueError("End date must follow the start date")
        except ValueError as error:
            raise HTTPException(422, str(error))
        rule = data.model_dump()
        rule["id"] = uuid.uuid4().hex
        with store.db() as db:
            db.execute(
                "INSERT INTO calendar_cadences(source_id,data,demo) VALUES(?,?,?)",
                (rule["id"], json.dumps(rule), data.demo),
            )
        return {"id": rule["id"]}

    @app.delete("/api/calendar-cadences/{identifier}")
    def remove_cadence(identifier: str):
        with store.db() as db:
            rows = list(db.execute("SELECT id,data FROM calendar_cadences"))
            found = next(
                (r for r in rows if str(json.loads(r["data"]).get("id")) == identifier),
                None,
            )
            if not found:
                raise HTTPException(404, "Cadence not found")
            db.execute("DELETE FROM calendar_cadences WHERE id=?", (found["id"],))
        return {"ok": True}

    @app.get("/api/backup")
    def export():
        return JSONResponse(
            notebook.export_notebook(store),
            headers={
                "Content-Disposition": f'attachment; filename="meridian-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json"'
            },
        )

    @app.post("/api/backup/restore")
    async def restore(request: Request):
        payload = await request.json()
        if app.state.jobs.running() or app.state.sync_lock.locked():
            raise HTTPException(
                409, "Wait for the Gmail import to finish before restoring a notebook"
            )
        try:
            saved = notebook.restore_notebook(store, payload)
            return {"ok": True, "safety_backup": saved.name}
        except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as error:
            raise HTTPException(
                422, "Backup validation failed; existing notebook was preserved"
            ) from error

    @app.post("/api/daybook/import")
    async def import_daybook(request: Request):
        try:
            return notebook.import_daybook(store, await request.json())
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as error:
            raise HTTPException(
                422, "DayBook notebook validation failed; existing data was preserved"
            ) from error

    @app.post("/api/activity/{identifier}/reopen")
    def reopen_activity(identifier: int):
        with store.db() as db:
            event = db.execute(
                "SELECT * FROM activity WHERE id=? AND voided=0", (identifier,)
            ).fetchone()
            if not event:
                raise HTTPException(404, "Completion is no longer available")
            if event["kind"] == "task":
                task = db.execute(
                    "SELECT * FROM tasks WHERE id=?", (event["entity_id"],)
                ).fetchone()
                if not task or task["deleted_at"]:
                    raise HTTPException(409, "Restore this task from Trash first")
                try:
                    notebook.complete_task(db, task, False)
                except ValueError as error:
                    raise HTTPException(409, str(error))
                db.execute(
                    "UPDATE tasks SET completed=0,updated_at=? WHERE id=?",
                    (stamp(), task["id"]),
                )
                db.execute("UPDATE activity SET voided=1 WHERE id=?", (identifier,))
            else:
                reminder = db.execute(
                    "SELECT * FROM reminders WHERE id=?", (event["entity_id"],)
                ).fetchone()
                if (
                    not reminder
                    or reminder["cycle"] != event["cycle"]
                    or not reminder["completed_at"]
                ):
                    raise HTTPException(
                        409,
                        "This reminder has started a new cycle. Its previous check-in stays in history.",
                    )
                db.execute(
                    "UPDATE reminders SET completed_at=NULL,updated_at=? WHERE id=?",
                    (stamp(), reminder["id"]),
                )
                db.execute("UPDATE activity SET voided=1 WHERE id=?", (identifier,))
        return {"ok": True}

    @app.get("/api/desktop")
    def desktop():
        today = datetime.now(TZ).date().isoformat()
        return {
            "tasks": [
                {
                    "id": str(t["id"]),
                    "title": t["title"],
                    "due": t.get("due_date")
                    or (
                        datetime.fromisoformat(t["due_at"])
                        .astimezone(TZ)
                        .date()
                        .isoformat()
                        if t["due_at"]
                        else ""
                    ),
                    "available": t.get("available_on") or "",
                    "completedAt": t.get("completed_at") if t["completed"] else None,
                    "deletedAt": t.get("deleted_at"),
                }
                for t in store.tasks(False)
                if not t["completed"]
                and t["confidence"] != "review"
                and (not t.get("available_on") or t["available_on"] <= today)
            ]
        }
