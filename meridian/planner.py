from datetime import datetime, timedelta
from .extract import TZ


def priority(task, now):
    if task["completed"]:
        return -1000
    if task["confidence"] == "review":
        return -100
    if not task["due_at"]:
        if task.get("due_date"):
            days = (datetime.fromisoformat(task["due_date"]).date() - now.date()).days
            return 100 - min(max(days * 24, -48), 120) + task.get("importance", 2) * 3
        return task.get("importance", 2) * 3
    hours = (datetime.fromisoformat(task["due_at"]) - now).total_seconds() / 3600
    return 120 - min(max(hours, -48), 120) + min(task["minutes"] / 15, 20)


def plan(tasks, blocks, now=None):
    now = now or datetime.now(TZ)
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    cursor = max(start, now.replace(second=0, microsecond=0) + timedelta(minutes=1))
    end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    intervals = sorted(
        [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in blocks
        ]
    )
    planned = {b["task_id"] for b in blocks if b["kind"] == "work"}
    result = []
    for task in sorted(tasks, key=lambda t: priority(t, now), reverse=True):
        if task["completed"] or task["confidence"] == "review" or task["id"] in planned:
            continue
        if not task["minutes"] or (
            task.get("available_on") and task["available_on"] > now.date().isoformat()
        ):
            continue
        if task.get("due_date") and task["due_date"] < now.date().isoformat():
            continue
        length = timedelta(minutes=task["minutes"])
        for a, b in intervals:
            if cursor < b and cursor + length > a:
                cursor = max(cursor, b)
        finish = cursor + length
        deadline = datetime.fromisoformat(task["due_at"]) if task["due_at"] else end
        if finish > end or finish > deadline:
            continue
        result.append(
            {
                "task_id": task["id"],
                "title": task["title"],
                "start": cursor.isoformat(),
                "end": finish.isoformat(),
                "kind": "work",
                "demo": task["demo"],
            }
        )
        cursor = finish + timedelta(minutes=15)
    return result
