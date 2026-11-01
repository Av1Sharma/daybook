"""Strict local Gmail admission: an actionable interview and an explicit date.

One task per message. No review candidates, guessed dates, or quoted-thread actions.
"""

import re
from datetime import date, datetime, time, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from .models import Candidate
from .extract import TZ, plain

POLICY = "interview-deadline-v1"
MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}
MONTH_PATTERN = "(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_PATTERNS = [
    re.compile(r"\b(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})(?=T|\b)"),
    re.compile(
        r"\b(?P<month_name>"
        + MONTH_PATTERN
        + r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s+(?P<year>20\d{2}))?\b",
        re.I,
    ),
    re.compile(
        r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month_name>"
        + MONTH_PATTERN
        + r")\.?(?:\s*,?\s+(?P<year>20\d{2}))?\b",
        re.I,
    ),
    re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>20\d{2}))?\b"),
]
REJECTION = re.compile(
    r"not (?:be )?(?:moving|proceeding|selected|able to offer)|no longer (?:available|consider)|position (?:has been |is )?(?:filled|closed)|will not (?:be )?(?:moving|proceeding|offer)|unfortunately|regret to inform|interview (?:has been |is )?cancel",
    re.I,
)
ACTION = re.compile(
    r"invit(?:e|ed|ation|ing).{0,140}interview|interview.{0,100}(?:invitation|due|deadline|scheduled|confirmed|\bby\b|\bon\b|expires)|(?:complete|finish|submit|schedule|book|confirm|choose|select|respond|reply|provide|send).{0,120}interview|interview.{0,100}(?:complete|finish|schedule|book|availability)|please.{0,40}(?:schedule|book|confirm|select|choose|provide|send|respond|reply)",
    re.I | re.S,
)
DEADLINE = re.compile(
    r"\b(?:due|deadline|by|before|until|expires?|expiry|no later than)\b", re.I
)
SCHEDULE = re.compile(
    r"\b(?:scheduled|confirmed|interview\s+(?:is\s+)?(?:on|at|for)|date\s*:)\b", re.I
)


def received_date(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value:
        try:
            return parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            pass
    return None


def current_message(body):
    lines = []
    for line in plain(body).splitlines():
        if re.match(
            r"\s*(?:On .+wrote:|[-_]{3,}\s*(?:Original|Forwarded) Message|Begin forwarded message:|From:\s)",
            line,
            re.I,
        ):
            break
        if not line.lstrip().startswith(">"):
            lines.append(line)
    return "\n".join(lines)


def _date(match, received):
    parts = match.groupdict()
    month = parts.get("month_name")
    month = (
        next(
            (v for k, v in MONTHS.items() if k.startswith(month.lower().rstrip("."))),
            None,
        )
        if month
        else int(parts["month"])
    )
    year = (
        int(parts["year"])
        if parts.get("year")
        else (received.astimezone(TZ).year if received else None)
    )
    if not year or not month:
        return None
    if not parts.get("year") and received.month == 12 and month == 1:
        year += 1
    try:
        return date(year, month, int(parts["day"]))
    except ValueError:
        return None


def _time(day, tail):
    match = re.match(
        r"(?:T|\s*(?:at\s+|,\s*)?)(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*(AM|PM)?(?:\s*(Z|[+-]\d{2}:\d{2}|EDT|EST|ET|PDT|PST|PT|CDT|CST|CT|MDT|MST|MT|UTC|GMT))?\b",
        tail,
        re.I,
    )
    if not match or (not match[2] and not match[3]):
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if match[3]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match[3].upper() == "PM" else 0)
    zone = (match[4] or "").upper()
    zones = {
        "ET": "America/New_York",
        "PT": "America/Los_Angeles",
        "CT": "America/Chicago",
        "MT": "America/Denver",
    }
    offsets = {
        "EST": -5,
        "EDT": -4,
        "PST": -8,
        "PDT": -7,
        "CST": -6,
        "CDT": -5,
        "MST": -7,
        "MDT": -6,
        "Z": 0,
        "UTC": 0,
        "GMT": 0,
    }
    tz = (
        ZoneInfo(zones[zone])
        if zone in zones
        else timezone(timedelta(hours=offsets[zone])) if zone in offsets else TZ
    )
    if zone.startswith(("+", "-")):
        sign = 1 if zone[0] == "+" else -1
        tz = timezone(sign * timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6])))
    try:
        return datetime.combine(day, time(hour, minute), tz)
    except ValueError:
        return None


def interview_candidates(
    subject, body, url="", source_id="gmail:manual", received=None
):
    received = received_date(received)
    body = current_message(body)
    text = subject + "\n" + body
    normalized = re.sub(r"\s+", " ", text)
    if not re.search(r"\binterviews?\b", normalized, re.I):
        return []
    if re.search(
        r"^(?:re:\s*)?(?:automatic reply|auto.?reply|out of (?:the )?office)|\b(?:tips|webinar|workshop|newsletter|interview prep guide)\b",
        subject,
        re.I,
    ):
        return []
    if re.search(r"assessment|coding challenge", subject, re.I) and not re.search(
        r"interview", subject, re.I
    ):
        return []
    if REJECTION.search(normalized) or not ACTION.search(normalized):
        return []
    found = []
    seen = set()
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(normalized):
            day = _date(match, received)
            if not day or (match.start(), day) in seen:
                continue
            seen.add((match.start(), day))
            # Dates must belong to an actual deadline or scheduled interview, not a footer/history.
            before = normalized[max(0, match.start() - 100) : match.start()]
            # A recruiter's notification timeline is not an action due from the user.
            if re.search(
                r"(?:notifi(?:ed|cation)|announce[ds]?|hear back|decisions?|applications? (?:close|closed)).{0,45}(?:by|on|before)\s*$",
                before,
                re.I,
            ):
                continue
            context = normalized[
                max(0, match.start() - 180) : min(len(normalized), match.end() + 100)
            ]
            is_deadline = bool(DEADLINE.search(before))
            scheduled = bool(SCHEDULE.search(before))
            if not (is_deadline or scheduled):
                continue
            if not re.search(r"interview", subject, re.I) and not re.search(
                r"interview", context, re.I
            ):
                continue
            timed = _time(day, normalized[match.end() :])
            found.append((0 if is_deadline else 1, day, match.start(), timed))
    if not found:
        return []
    _, day, _, timed = sorted(found, key=lambda value: (value[0], value[1], value[2]))[
        0
    ]
    title = (
        re.sub(r"^(?:re|fw|fwd):\s*", "", subject, flags=re.I).strip()
        or "Interview deadline"
    )
    return [
        Candidate(
            title=title[:230],
            course="Gmail",
            category="career",
            source_type="gmail",
            source_url=url,
            source_id=source_id + ":interview-deadline",
            evidence=text[:20000],
            confidence="confirmed",
            minutes=0,
            due_at=timed,
            due_date=None if timed else day,
            destination="Gmail",
        )
    ]


def retire_legacy_suggestions(store):
    """Recoverably remove only old automatic Gmail suggestions. Never touch notebooks/manual work."""
    from .notebook import backup
    from .store import stamp

    with store.db() as db:
        if db.execute(
            "SELECT 1 FROM syncs WHERE source='gmail_filter' AND status=?", (POLICY,)
        ).fetchone():
            return 0
        rows = list(
            db.execute(
                """SELECT t.id FROM tasks t WHERE t.demo=0 AND t.notebook_id IS NULL
          AND t.completed=0 AND t.deleted_at IS NULL AND t.identity NOT LIKE 'gmail-interview:%'
          AND EXISTS(SELECT 1 FROM evidence e WHERE e.task_id=t.id AND e.source_type='gmail')
          AND NOT EXISTS(SELECT 1 FROM evidence e WHERE e.task_id=t.id AND e.source_type!='gmail')
          AND NOT EXISTS(SELECT 1 FROM changes c WHERE c.task_id=t.id AND c.message LIKE 'Manual update:%')"""
            )
        )
    if not rows:
        return 0
    backup(store, "before-interview-email-filter")
    now = stamp()
    with store.db() as db:
        for row in rows:
            db.execute(
                "UPDATE tasks SET deleted_at=?,updated_at=? WHERE id=?",
                (now, now, row[0]),
            )
            db.execute("DELETE FROM blocks WHERE task_id=? AND kind='work'", (row[0],))
            db.execute(
                "INSERT INTO changes(task_id,message,created_at) VALUES(?,?,?)",
                (
                    row[0],
                    "Excluded by interview-only email policy. Recoverable from Trash.",
                    now,
                ),
            )
        db.execute(
            "INSERT OR REPLACE INTO syncs VALUES(?,?,?,?)",
            ("gmail_filter", POLICY, str(len(rows)), now),
        )
        db.execute("UPDATE gmail_progress SET state='superseded'")
        db.execute(
            "INSERT OR REPLACE INTO syncs VALUES('gmail','paused',?,?)",
            (
                "Interview-only filter applied. Rescan interview emails with clear dates.",
                now,
            ),
        )
    return len(rows)
