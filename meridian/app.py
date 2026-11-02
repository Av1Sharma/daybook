import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from .connectors import canvas_sync, gmail_sync
from .demo import seed
from .extract import extract, extract_ai, TZ
from .models import (
    Candidate,
    ImportRequest,
    TaskUpdate,
    BlockRequest,
    ReminderInput,
    ReminderAction,
    WeeklyNotes,
)
from . import journal, notebook, notebook_api
from .settings import Settings
from .oauth import GoogleOAuth
from .sync_jobs import SyncJobs
from .models import ConnectionSettings
from .planner import plan, priority
from .store import Store, stamp


def create_app(db_path=None):
    store = Store(db_path or os.getenv("MERIDIAN_DB", "data/meridian.db"))
    settings = Settings(
        os.getenv("MERIDIAN_SETTINGS_DIR") or str(Path(store.path).parent / "settings")
    )
    settings.load()
    oauth = GoogleOAuth(settings)
    seed(store)
    journal.seed_reminders(store)
    from .gmail_filter import retire_legacy_suggestions

    retire_legacy_suggestions(store)
    token = secrets.token_urlsafe(32)
    sync_lock = asyncio.Lock()
    jobs = SyncJobs(store, sync_lock)

    @asynccontextmanager
    async def lifespan(app):
        if (
            os.getenv("MERIDIAN_DESKTOP") == "1"
            and jobs.resume_needed()
            and (
                os.getenv("GOOGLE_ACCOUNTS")
                or os.getenv("GOOGLE_REFRESH_TOKEN")
                or os.getenv("GMAIL_ACCESS_TOKEN")
            )
        ):
            jobs.start()
        yield
        await jobs.stop()

    app = FastAPI(title="Daybook", version="2.0.0", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    app.state.oauth = oauth
    notebook_api.attach(app, store)
    from . import syllabus
    syllabus.attach(app, store)
    jobs.attach(app)
    app.state.jobs = jobs
    app.state.sync_lock = sync_lock
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("localhost", "127.0.0.1", "testserver"):
            return Response("Local access only", status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-meridian-token") != token:
                return Response(
                    "Reload Daybook before making changes", status_code=403
                )
            origin = request.headers.get("origin")
            if origin and origin not in (
                "http://" + request.headers["host"],
                "https://" + request.headers["host"],
            ):
                return Response("Cross-origin request rejected", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {
            "app": "meridian",
            "version": "2.0.0",
            "desktop": os.getenv("MERIDIAN_DESKTOP") == "1",
        }

    @app.get("/api/connections")
    def connections():
        return settings.status()

    @app.put("/api/connections")
    def configure_connections(data: ConnectionSettings):
        settings.set("CANVAS_BASE_URL", data.canvas_url)
        for key, value in [
            ("CANVAS_TOKEN", data.canvas_token),
            ("GOOGLE_CLIENT_ID", data.google_client_id),
            ("GOOGLE_CLIENT_SECRET", data.google_client_secret),
        ]:
            if value.strip():
                settings.set(key, value.strip())
        return settings.status()

    @app.delete("/api/connections/{provider}")
    def disconnect(provider: str):
        keys = {
            "canvas": ["CANVAS_TOKEN"],
            "gmail": [
                "GOOGLE_ACCOUNTS",
                "GOOGLE_REFRESH_TOKEN",
                "GMAIL_ACCESS_TOKEN",
                "GOOGLE_EMAIL",
            ],
        }.get(provider)
        if not keys:
            raise HTTPException(404, "Unknown provider")
        for key in keys:
            settings.set(key, "")
        return settings.status()

    @app.post("/api/oauth/google/start")
    def start_google(request: Request):
        try:
            return {
                "url": oauth.begin(
                    str(request.base_url).rstrip("/") + "/api/oauth/google/callback"
                )
            }
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.get("/api/oauth/google/callback")
    async def finish_google(state: str = "", code: str = "", error: str = ""):
        try:
            if error or not code:
                oauth.pending.pop(state, None)
                return RedirectResponse(
                    "/?connection=declined#sources", status_code=303
                )
            await oauth.finish(state, code)
            return RedirectResponse("/?connection=connected#sources", status_code=303)
        except Exception:
            return RedirectResponse("/?connection=failed#sources", status_code=303)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/state")
    def state(demo: bool = False):
        tasks = store.tasks(demo)
        now = datetime.now(TZ)
        tasks.sort(key=lambda t: priority(t, now), reverse=True)
        with store.db() as db:
            blocks = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM blocks WHERE demo=? ORDER BY start", (demo,)
                )
            ]
            syncs = [dict(r) for r in db.execute("SELECT * FROM syncs")]
        active = [
            t
            for t in tasks
            if not t["completed"]
            and t["confidence"] != "review"
            and (
                not t.get("available_on") or t["available_on"] <= now.date().isoformat()
            )
        ]
        return {
            "tasks": tasks,
            "reminders": journal.reminders(store, demo),
            "blocks": blocks,
            "syncs": syncs,
            "token": token,
            "now": now.isoformat(),
            "timezone": str(TZ),
            "demo": demo,
            "connection_status": settings.status(),
            "connections": {
                "canvas": bool(os.getenv("CANVAS_TOKEN")),
                "gmail": bool(
                    os.getenv("GOOGLE_ACCOUNTS")
                    or os.getenv("GMAIL_ACCESS_TOKEN")
                    or os.getenv("GOOGLE_REFRESH_TOKEN")
                ),
                "ai": os.getenv("MERIDIAN_AI") == "1"
                and bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
            },
            "briefing": {
                "open": len(active),
                "review": sum(
                    t["confidence"] == "review" and not t["completed"] for t in tasks
                ),
                "due_soon": sum(
                    t["confidence"] != "review"
                    and (
                        (
                            bool(t["due_at"])
                            and datetime.fromisoformat(t["due_at"])
                            <= now + timedelta(days=2)
                        )
                        or (
                            bool(t.get("due_date"))
                            and t["due_date"]
                            <= (now.date() + timedelta(days=2)).isoformat()
                        )
                    )
                    for t in active
                ),
                "minutes": sum(
                    t["minutes"] for t in active if t["confidence"] != "review"
                ),
                "summary": (
                    f"Start with {active[0]['title']}."
                    if active and active[0]["confidence"] != "review"
                    else (
                        "Your next clear step starts with reviewing the evidence."
                        if active
                        else "A clear day starts here. Connect your sources or import a syllabus to build your plan."
                    )
                ),
            },
        }

    def get_task(db, task_id):
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        return row

    @app.patch("/api/tasks/{task_id}")
    def update(task_id: int, data: TaskUpdate):
        with store.db() as db:
            row = get_task(db, task_id)
            if data.confirm and not (data.due_at or row["due_at"]):
                raise HTTPException(
                    422, "Choose a deadline with a timezone before confirming"
                )
            if data.completed is not None:
                if bool(row["completed"]) != data.completed:
                    try:
                        notebook.complete_task(db, row, data.completed)
                    except ValueError as error:
                        raise HTTPException(409, str(error))
                    journal.record_task(db, task_id, data.completed)
                db.execute(
                    "UPDATE tasks SET completed=? WHERE id=?", (data.completed, task_id)
                )
                if data.completed:
                    db.execute(
                        "DELETE FROM blocks WHERE task_id=? AND kind='work'", (task_id,)
                    )
            if data.minutes is not None:
                db.execute(
                    "UPDATE tasks SET minutes=? WHERE id=?", (data.minutes, task_id)
                )
            if data.clear_deadline:
                db.execute(
                    "UPDATE tasks SET due_at=NULL,due_date=NULL WHERE id=?", (task_id,)
                )
                db.execute(
                    "DELETE FROM blocks WHERE task_id=? AND kind='work'", (task_id,)
                )
            if data.due_at:
                db.execute(
                    "UPDATE tasks SET due_at=?,due_date=NULL WHERE id=?",
                    (data.due_at.isoformat(), task_id),
                )
                db.execute(
                    "DELETE FROM blocks WHERE task_id=? AND kind='work'", (task_id,)
                )
            if data.confirm:
                db.execute(
                    "UPDATE tasks SET confidence='confirmed' WHERE id=?", (task_id,)
                )
            db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (stamp(), task_id))
            db.execute(
                "INSERT INTO changes(task_id,message,created_at) VALUES(?,?,?)",
                (
                    task_id,
                    "Manual update: " + data.model_dump_json(exclude_none=True),
                    stamp(),
                ),
            )
        return {"ok": True}

    @app.post("/api/import")
    async def import_text(data: ImportRequest):
        try:
            if os.getenv("MERIDIAN_AI") == "1":
                candidates = await extract_ai(
                    data.text, data.course, data.kind, data.url
                )
            else:
                candidates = extract(
                    data.text,
                    data.course,
                    data.kind,
                    data.url,
                    start=data.semester_start,
                    end=data.semester_end,
                )
            return {**store.ingest(candidates), "candidates": len(candidates)}
        except (ValueError, KeyError) as e:
            raise HTTPException(422, str(e))
        except Exception:
            raise HTTPException(
                502,
                "Extraction failed. Your source has not been imported; check provider configuration.",
            )

    @app.post("/api/tasks")
    def add_task(data: Candidate):
        if data.source_type != "manual" or data.demo:
            raise HTTPException(422, "Use import for source data")
        return store.ingest([data])

    @app.post("/api/reminders")
    def add_reminder(data: ReminderInput, demo: bool = False):
        with store.db() as db:
            cursor = db.execute(
                "INSERT INTO reminders(title,notes,category,minutes,due_at,demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    data.title,
                    data.notes,
                    data.category,
                    data.minutes,
                    data.due_at.isoformat() if data.due_at else None,
                    demo,
                    stamp(),
                    stamp(),
                ),
            )
        return {"id": cursor.lastrowid}

    @app.put("/api/reminders/{reminder_id}")
    def edit_reminder(reminder_id: int, data: ReminderInput, demo: bool = False):
        with store.db() as db:
            journal.get_reminder(db, reminder_id, demo)
            db.execute(
                "UPDATE reminders SET title=?,notes=?,category=?,minutes=?,due_at=?,updated_at=? WHERE id=?",
                (
                    data.title,
                    data.notes,
                    data.category,
                    data.minutes,
                    data.due_at.isoformat() if data.due_at else None,
                    stamp(),
                    reminder_id,
                ),
            )
        return {"ok": True}

    @app.post("/api/reminders/{reminder_id}/action")
    def reminder_action(reminder_id: int, data: ReminderAction, demo: bool = False):
        return journal.act(store, reminder_id, data.action, demo)

    @app.get("/api/weekly-review")
    def weekly_review(week: date | None = None, demo: bool = False):
        return journal.review(store, week, demo)

    @app.put("/api/weekly-review/{week}")
    def save_weekly_notes(week: date, data: WeeklyNotes, demo: bool = False):
        start = journal.monday(week).isoformat()
        with store.db() as db:
            db.execute(
                "INSERT INTO weekly_notes(week_start,demo,wins,friction,next_focus,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(week_start,demo) DO UPDATE SET wins=excluded.wins,friction=excluded.friction,next_focus=excluded.next_focus,updated_at=excluded.updated_at",
                (start, demo, data.wins, data.friction, data.next_focus, stamp()),
            )
        return {"ok": True, "week_start": start}

    @app.post("/api/sync")
    async def sync():
        if sync_lock.locked():
            raise HTTPException(409, "A sync is already running")
        results = {}
        async with sync_lock:
            for name, fn in [("canvas", canvas_sync), ("gmail", gmail_sync)]:
                if name == "canvas" and not os.getenv("CANVAS_TOKEN"):
                    message = "Use course material import for Canvas."
                    store.sync_status(name, "skipped", message)
                    results[name] = {"status": "skipped", "detail": message}
                    continue
                try:
                    items = await fn()
                    counts = store.ingest(items)
                    store.sync_status(name, "ok", json.dumps(counts))
                    results[name] = {"status": "ok", **counts}
                except Exception:
                    # Never expose upstream URLs, tokens, message bodies, or raw exceptions.
                    message = "Sync failed. Check credentials, permissions, and network access. Previous tasks were preserved."
                    store.sync_status(name, "error", message)
                    results[name] = {"status": "error", "detail": message}
        return results

    @app.post("/api/plan")
    def generate_plan(demo: bool = False):
        with store.db() as db:
            blocks = [
                dict(r)
                for r in db.execute("SELECT * FROM blocks WHERE demo=?", (demo,))
            ]
            suggestions = plan(store.tasks(demo), blocks)
            for b in suggestions:
                db.execute(
                    "INSERT INTO blocks(task_id,title,start,end,kind,demo) VALUES(?,?,?,?,?,?)",
                    tuple(
                        b[k]
                        for k in ("task_id", "title", "start", "end", "kind", "demo")
                    ),
                )
        return {"scheduled": len(suggestions)}

    @app.post("/api/blocks")
    def add_block(data: BlockRequest):
        end = data.start + timedelta(minutes=data.minutes)
        with store.db() as db:
            demo = get_task(db, data.task_id)["demo"] if data.task_id else False
            rows = db.execute(
                "SELECT start,end FROM blocks WHERE demo=?", (demo,)
            ).fetchall()
            if any(
                data.start < datetime.fromisoformat(r["end"])
                and end > datetime.fromisoformat(r["start"])
                for r in rows
            ):
                raise HTTPException(
                    409, "This block overlaps an existing calendar event"
                )
            if data.task_id and data.kind == "work":
                t = get_task(db, data.task_id)
                if t["completed"]:
                    raise HTTPException(422, "Completed tasks cannot be scheduled")
                if t["confidence"] == "review":
                    raise HTTPException(422, "Review this task before scheduling it")
                if t["due_at"] and end > datetime.fromisoformat(t["due_at"]):
                    raise HTTPException(422, "Work block ends after the deadline")
            db.execute(
                "INSERT INTO blocks(task_id,title,start,end,kind,demo) VALUES(?,?,?,?,?,?)",
                (
                    data.task_id,
                    data.title,
                    data.start.isoformat(),
                    end.isoformat(),
                    data.kind,
                    demo,
                ),
            )
        return {"ok": True}

    @app.delete("/api/blocks/{block_id}")
    def remove_block(block_id: int):
        with store.db() as db:
            if not db.execute("DELETE FROM blocks WHERE id=?", (block_id,)).rowcount:
                raise HTTPException(404, "Block not found")
        return {"ok": True}

    @app.get("/api/calendar.ics")
    def calendar(demo: bool = False):
        def esc(s):
            return (
                s.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\r", "")
            )

        def utc(s):
            return (
                datetime.fromisoformat(s)
                .astimezone(timezone.utc)
                .strftime("%Y%m%dT%H%M%SZ")
            )

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Meridian//Planner//EN",
            "CALSCALE:GREGORIAN",
        ]
        for t in store.tasks(demo):
            if (
                t["completed"]
                or t["confidence"] == "review"
                or not (t["due_at"] or t.get("due_date"))
            ):
                continue
            lines += [
                "BEGIN:VEVENT",
                f'UID:task-{t["id"]}@meridian.local',
                f'DTSTAMP:{utc(t["updated_at"])}',
                (
                    f'DTSTART:{utc(t["due_at"])}'
                    if t["due_at"]
                    else f'DTSTART;VALUE=DATE:{t["due_date"].replace("-", "")}'
                ),
                "SUMMARY:"
                + esc(
                    t["title"]
                    + (" (expected)" if t["confidence"] == "expected" else "")
                ),
                "DESCRIPTION:" + esc(t["course"] + " · " + t["destination"]),
                "END:VEVENT",
            ]
        for event in notebook.events(store, demo):
            if event["tentative"] or event["linked_task_id"]:
                continue
            start = (
                datetime.combine(
                    date.fromisoformat(event["date"]),
                    datetime.strptime(event["time"], "%H:%M").time(),
                    TZ,
                ).isoformat()
                if event["time"]
                else None
            )
            lines += [
                "BEGIN:VEVENT",
                f'UID:event-{event["id"]}@meridian.local',
                f"DTSTAMP:{utc(stamp())}",
                (
                    f"DTSTART:{utc(start)}"
                    if start
                    else "DTSTART;VALUE=DATE:" + event["date"].replace("-", "")
                ),
                "SUMMARY:" + esc(event["title"]),
                "DESCRIPTION:" + esc(event["notes"]),
                "LOCATION:" + esc(event["location"]),
            ]
            if not start:
                lines += [
                    "DTEND;VALUE=DATE:"
                    + (
                        date.fromisoformat(event["end_date"] or event["date"])
                        + timedelta(days=1)
                    ).strftime("%Y%m%d")
                ]
            elif event["end_time"]:
                finish = datetime.combine(
                    date.fromisoformat(event["end_date"] or event["date"]),
                    datetime.strptime(event["end_time"], "%H:%M").time(),
                    TZ,
                ).isoformat()
                lines += ["DTEND:" + utc(finish)]
            lines += ["END:VEVENT"]
        lines += ["END:VCALENDAR"]
        # RFC 5545 folding by UTF-8 octets.
        folded = []
        for line in lines:
            part = ""
            for char in line:
                if len((part + char).encode()) > 73:
                    folded.append(part)
                    part = " " + char
                else:
                    part += char
            folded.append(part)
        return Response(
            "\r\n".join(folded) + "\r\n",
            media_type="text/calendar",
            headers={"Content-Disposition": 'attachment; filename="meridian.ics"'},
        )

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app


app = create_app()
