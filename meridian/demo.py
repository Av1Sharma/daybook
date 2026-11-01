from datetime import datetime, timedelta
from .extract import TZ
from .models import Candidate


def seed(store):
    if store.tasks(True):
        return
    now = datetime.now(TZ)

    def due(offset, hour=23, minute=59):
        return (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

    items = [
        (
            "Problem set 06: Vector spaces",
            "MATH 2210",
            "academic",
            1,
            90,
            "assignment",
            "confirmed",
            "Canvas",
            "Work through problems 1–8 on vector spaces and linear independence.",
        ),
        (
            "Complete software engineering assessment",
            "Stripe · Summer 2027",
            "career",
            2,
            75,
            "gmail",
            "confirmed",
            "Gmail",
            "Please complete your online assessment by the deadline in your invitation.",
        ),
        (
            "Prelim 2 preparation",
            "CS 2110",
            "academic",
            4,
            120,
            "syllabus",
            "confirmed",
            "Canvas",
            "Prelim 2 covers recursion, trees, and sorting. Review the practice exam.",
        ),
        (
            "Homework 08: Induction",
            "CS 2800",
            "academic",
            2,
            60,
            "syllabus",
            "expected",
            "Gradescope",
            "Homework is due every Friday at 11:59 PM on Gradescope.",
        ),
        (
            "Send interview availability",
            "Figma · Product engineering",
            "career",
            1,
            20,
            "gmail",
            "confirmed",
            "Gmail",
            "Reply with three windows of availability for a 30-minute interview.",
        ),
        (
            "Quiz 4: Subjunctive",
            "SPAN 2090",
            "academic",
            None,
            30,
            "syllabus",
            "review",
            "Canvas",
            "Quiz 4 will take place next week. Exact date to be announced.",
        ),
        (
            "Problem set 05: Bases",
            "MATH 2210",
            "academic",
            0,
            60,
            "announcement",
            "review",
            "Canvas",
            "The announcement says Sunday; the syllabus lists Friday. Confirm the extension.",
        ),
        (
            "Read chapter 7",
            "CS 2110",
            "academic",
            3,
            35,
            "manual",
            "confirmed",
            "Canvas",
            "Read the chapter on binary search trees before discussion.",
        ),
    ]
    for i, (
        title,
        course,
        category,
        offset,
        minutes,
        kind,
        confidence,
        destination,
        evidence,
    ) in enumerate(items):
        store.ingest(
            [
                Candidate(
                    title=title,
                    course=course,
                    category=category,
                    due_at=due(offset) if offset is not None else None,
                    minutes=minutes,
                    source_id=f"demo:{i}",
                    source_type=kind,
                    source_url="",
                    evidence=evidence,
                    confidence=confidence,
                    destination=destination,
                    demo=True,
                )
            ]
        )
    with store.db() as db:
        for hour, title in [
            (10, "CS 2110 · Object-oriented programming"),
            (14, "MATH 2210 · Discussion"),
        ]:
            a = due(0, hour, 0)
            b = a + timedelta(minutes=50)
            db.execute(
                "INSERT INTO blocks(title,start,end,kind,demo) VALUES(?,?,?,?,1)",
                (title, a.isoformat(), b.isoformat(), "busy"),
            )
