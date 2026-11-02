from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Candidate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    course: str = Field(default="Personal", max_length=100)
    category: Literal["academic", "career", "personal"] = "academic"
    due_at: datetime | None = None
    due_date: date | None = None
    confidence: Literal["confirmed", "expected", "review"] = "review"
    minutes: int = Field(default=60, ge=0, le=600)
    destination: str = Field(default="Canvas", max_length=100)
    source_id: str = Field(min_length=1, max_length=250)
    source_type: Literal[
        "assignment", "syllabus", "announcement", "file", "gmail", "manual"
    ]
    source_url: str = Field(default="", max_length=2000)
    evidence: str = Field(min_length=1, max_length=20000)
    submitted: bool = False
    demo: bool = False

    @field_validator("due_at")
    @classmethod
    def aware(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Deadline must include a timezone")
        return value

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Source links must use HTTPS")
        return value


class TaskUpdate(BaseModel):
    completed: bool | None = None
    due_at: datetime | None = None
    confirm: bool = False
    minutes: int | None = Field(default=None, ge=5, le=600)
    clear_deadline: bool = False
    _aware = field_validator("due_at")(Candidate.aware.__func__)


class ImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    course: str = Field(default="Imported", max_length=100)
    kind: Literal["syllabus", "gmail", "announcement", "file"] = "syllabus"
    url: str = ""
    semester_start: str | None = None
    semester_end: str | None = None


class BlockRequest(BaseModel):
    task_id: int | None = None
    title: str = Field(min_length=1, max_length=250)
    start: datetime
    minutes: int = Field(ge=5, le=600)
    kind: Literal["work", "busy"] = "work"
    _aware = field_validator("start")(Candidate.aware.__func__)


class ReminderInput(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    notes: str = Field(default="", max_length=4000)
    category: Literal["academic", "career", "personal"] = "career"
    minutes: int = Field(default=15, ge=5, le=600)
    due_at: datetime | None = None
    _aware = field_validator("due_at")(Candidate.aware.__func__)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Give your reminder a title")
        return value.strip()


class ReminderAction(BaseModel):
    action: Literal["complete", "rearm", "archive", "restore", "undo"]


class WeeklyNotes(BaseModel):
    wins: str = Field(default="", max_length=4000)
    friction: str = Field(default="", max_length=4000)
    next_focus: str = Field(default="", max_length=4000)


class ConnectionSettings(BaseModel):
    canvas_url: str = Field(default="https://canvas.cornell.edu", max_length=500)
    canvas_token: str = Field(default="", max_length=1000)
    google_client_id: str = Field(default="", max_length=500)
    google_client_secret: str = Field(default="", max_length=1000)

    @field_validator("canvas_url")
    @classmethod
    def canvas_origin(cls, value):
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Use the HTTPS origin of your Canvas site")
        return value.rstrip("/")


class NotebookTask(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notebook_category: Literal[
        "Academics / classes",
        "LeetCode / coding",
        "Internships / jobs",
        "Projects",
        "Personal",
    ] = "Personal"
    course: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=20000)
    due_date: str | None = None
    due_at: datetime | None = None
    _aware = field_validator("due_at")(Candidate.aware.__func__)
    importance: int = Field(default=2, ge=1, le=3)
    repeat_rule: Literal["none", "daily", "weekly"] = "none"
    minutes: int = Field(default=0, ge=0, le=1440)
    demo: bool = False


class ReferenceNote(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    items: list[str | dict] = Field(default_factory=list, max_length=1000)
    scope: Literal["general", "internships"] = "general"
    archived: bool = False
    demo: bool = False


class CalendarEvent(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    course: str = Field(default="", max_length=100)
    date: str
    end_date: str | None = None
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    notes: str = Field(default="", max_length=20000)
    location: str = Field(default="", max_length=500)
    tentative: bool = False
    kind: str = Field(default="deadline", max_length=50)
    source: str = Field(default="", max_length=2000)
    demo: bool = False


class CalendarCadence(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    course: str = Field(min_length=1, max_length=100)
    start: str
    end: str
    weekdays: list[int] = Field(min_length=1, max_length=7)
    demo: bool = False

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, values):
        if any(v < 0 or v > 6 for v in values):
            raise ValueError("Choose weekdays from Sunday to Saturday")
        return sorted(set(values))
