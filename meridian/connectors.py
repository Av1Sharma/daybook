"""Read-only provider adapters. Never send Canvas credentials to file/CDN URLs."""

import base64
import asyncio
import json
import hashlib
from datetime import datetime, timezone
from urllib.parse import quote
import io
import os
from urllib.parse import urlparse
import httpx
from pypdf import PdfReader
from .extract import extract, extract_ai, plain
from .models import Candidate
from .gmail_filter import interview_candidates, POLICY


async def material(text, course, kind, url, sid):
    if os.getenv("MERIDIAN_AI") == "1":
        return await extract_ai(text, course, kind, url, sid)
    return extract(
        text,
        course,
        kind,
        url,
        sid,
        os.getenv("SEMESTER_START"),
        os.getenv("SEMESTER_END"),
    )


async def pages(client, url, params=None):
    origin = urlparse(url).netloc
    visited = set()
    while url:
        if url in visited or len(visited) > 100:
            raise ValueError("Invalid or excessive pagination")
        if urlparse(url).scheme != "https" or urlparse(url).netloc != origin:
            raise ValueError("Refusing cross-origin pagination")
        visited.add(url)
        res = await client.get(url, params=params)
        res.raise_for_status()
        yield res.json()
        url = res.links.get("next", {}).get("url")
        params = None


async def canvas_sync():
    base = os.getenv("CANVAS_BASE_URL", "https://canvas.cornell.edu").rstrip("/")
    if urlparse(base).scheme != "https":
        raise ValueError("Canvas URL must use HTTPS")
    token = os.getenv("CANVAS_TOKEN")
    if not token:
        raise ValueError("Canvas is not configured")
    out = []
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as client:
        async for courses in pages(
            client,
            base + "/api/v1/courses",
            {
                "enrollment_state": "active",
                "include[]": "syllabus_body",
                "per_page": 100,
            },
        ):
            for c in courses:
                cid, course = c["id"], c.get("course_code") or c.get(
                    "name", str(c["id"])
                )
                root = f"{base}/courses/{cid}"
                if c.get("syllabus_body"):
                    out.extend(
                        await material(
                            c["syllabus_body"],
                            course,
                            "syllabus",
                            root + "/assignments/syllabus",
                            f"canvas:{cid}:syllabus",
                        )
                    )
                async for assignments in pages(
                    client,
                    f"{base}/api/v1/courses/{cid}/assignments",
                    {"include[]": "submission", "per_page": 100},
                ):
                    for a in assignments:
                        out.append(
                            Candidate(
                                title=a["name"],
                                course=course,
                                due_at=a.get("due_at"),
                                confidence="confirmed" if a.get("due_at") else "review",
                                source_id=f'canvas:{cid}:assignment:{a["id"]}',
                                source_type="assignment",
                                source_url=a.get("html_url", root),
                                evidence=f'{a["name"]}\nDue: {a.get("due_at") or "Not specified"}\n{plain(a.get("description") or "")}'[
                                    :20000
                                ],
                                submitted=a.get("submission", {}).get("workflow_state")
                                in ("submitted", "graded"),
                                destination=(
                                    "Gradescope"
                                    if "gradescope"
                                    in (a.get("description") or "").lower()
                                    else "Canvas"
                                ),
                            )
                        )
                async for announcements in pages(
                    client,
                    base + "/api/v1/announcements",
                    {"context_codes[]": f"course_{cid}", "per_page": 100},
                ):
                    for a in announcements:
                        out.extend(
                            await material(
                                a.get("message", ""),
                                course,
                                "announcement",
                                a.get("html_url", root),
                                f'canvas:{cid}:announcement:{a["id"]}',
                            )
                        )
                # Files include uploaded syllabi and handouts; module file references also resolve here.
                async for files in pages(
                    client, f"{base}/api/v1/courses/{cid}/files", {"per_page": 100}
                ):
                    for f in files:
                        if f.get("locked_for_user") or f.get("size", 0) > 10_000_000:
                            continue
                        if f.get("content-type") != "application/pdf":
                            continue
                        async with httpx.AsyncClient(
                            timeout=30, follow_redirects=True
                        ) as public:
                            # Canvas's signed URL is sufficient. No bearer token on redirect.
                            url = f.get("url", "")
                            if not url.startswith("https://"):
                                continue
                            res = await public.get(url)
                            res.raise_for_status()
                        if len(res.content) > 10_000_000:
                            continue
                        reader = PdfReader(io.BytesIO(res.content))
                        text = "\n".join(
                            p.extract_text() or "" for p in reader.pages[:100]
                        )
                        out.extend(
                            await material(
                                text,
                                course,
                                "file",
                                root + f'/files/{f["id"]}',
                                f'canvas:{cid}:file:{f["id"]}',
                            )
                        )
    return out


def mime_text(payload):
    if payload.get("mimeType") in ("text/plain", "text/html"):
        data = payload.get("body", {}).get("data", "")
        return plain(
            base64.urlsafe_b64decode(data + "=" * ((-len(data)) % 4)).decode(
                "utf-8", errors="replace"
            )
        )
    parts = payload.get("parts", [])
    preferred = [p for p in parts if p.get("mimeType") == "text/plain"] or parts
    return "\n".join(mime_text(p) for p in preferred)


async def gmail_sync(store=None):
    accounts = json.loads(os.getenv("GOOGLE_ACCOUNTS") or "{}")
    if not accounts:
        return await gmail_account_sync(
            os.getenv("GOOGLE_REFRESH_TOKEN"),
            os.getenv("GMAIL_ACCESS_TOKEN"),
            store=store,
        )
    out = []
    totals = {"created": 0, "updated": 0, "unchanged": 0, "processed": 0, "cached": 0}
    failures = []
    blocked = []
    for email, refresh_token in accounts.items():
        try:
            result = (
                await gmail_account_sync(refresh_token, None, email, store=store)
                if store
                else await gmail_account_sync(refresh_token, None, email)
            )
            if store:
                for key in totals:
                    totals[key] += result[key]
            else:
                out.extend(result)
        except Exception as error:
            if not store:
                raise
            failures.append(email)
            retryable = isinstance(error, (httpx.TransportError, TimeoutError))
            if isinstance(error, httpx.HTTPStatusError):
                response = error.response
                retryable = response.status_code == 429 or response.status_code >= 500
                if response.status_code == 403:
                    try:
                        retryable = any(
                            e.get("reason")
                            in ("rateLimitExceeded", "userRateLimitExceeded")
                            for e in response.json().get("error", {}).get("errors", [])
                        )
                    except (ValueError, TypeError, AttributeError):
                        pass
            if not retryable:
                blocked.append(email)
            store.gmail_progress(
                email, os.getenv("GMAIL_QUERY", GMAIL_QUERY), state="paused"
            )
    return (
        {
            **totals,
            "partial": bool(failures),
            "failed_accounts": failures,
            "blocked_accounts": blocked,
        }
        if store
        else out
    )


async def gmail_get(client, url, params=None):
    """Retry temporary Gmail quota errors without swallowing permission failures."""
    for attempt in range(8):
        response = await client.get(url, params=params)
        quota = response.status_code == 429
        if response.status_code == 403:
            try:
                reasons = {
                    item.get("reason")
                    for item in response.json().get("error", {}).get("errors", [])
                }
                quota = bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded"})
            except (ValueError, TypeError, AttributeError):
                quota = False
        if not quota or attempt == 7:
            response.raise_for_status()
            return response
        try:
            retry_after = float(response.headers.get("Retry-After", "0"))
        except ValueError:
            retry_after = 0
        await asyncio.sleep(min(60, max(5 * 2**attempt, retry_after)))


GMAIL_QUERY = (
    "newer_than:30d {interview interviews} -category:promotions -category:social"
)


async def gmail_account_sync(refresh_token=None, token=None, email=None, store=None):
    async with httpx.AsyncClient(timeout=30) as auth:
        if refresh_token and os.getenv("GOOGLE_CLIENT_ID"):
            res = await auth.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": os.environ["GOOGLE_CLIENT_ID"],
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            res.raise_for_status()
            token = res.json()["access_token"]
    if not token:
        raise ValueError("Gmail is not configured")
    out = []
    totals = {"created": 0, "updated": 0, "unchanged": 0, "processed": 0, "cached": 0}
    query = os.getenv("GMAIL_QUERY", GMAIL_QUERY)
    mode = hashlib.sha256(
        json.dumps(
            [
                POLICY,
                os.getenv("MERIDIAN_AI") == "1",
                os.getenv("OPENAI_MODEL"),
                os.getenv("MERIDIAN_TIMEZONE", "America/New_York"),
                os.getenv("SEMESTER_START"),
                os.getenv("SEMESTER_END"),
            ]
        ).encode()
    ).hexdigest()
    known = store.gmail_known(email, mode) if store and email else set()
    if store and email:
        store.gmail_progress(email, query, mode=mode)
    page_token = None
    seen = set()
    async with httpx.AsyncClient(
        timeout=30, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        while True:
            params = {
                "q": query,
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            res = await gmail_get(
                client,
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                params=params,
            )
            res.raise_for_status()
            data = res.json()
            for m in data.get("messages", []):
                if m["id"] in known:
                    totals["cached"] += 1
                    continue
                r = await gmail_get(
                    client,
                    f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{m["id"]}',
                    params={"format": "full"},
                )
                r.raise_for_status()
                message = r.json()
                payload = message.get("payload", {})
                headers = {
                    h["name"].lower(): h["value"] for h in payload.get("headers", [])
                }
                text = headers.get("subject", "") + "\n" + mime_text(payload)
                try:
                    received = (
                        datetime.fromtimestamp(
                            int(message.get("internalDate", "0")) / 1000, timezone.utc
                        )
                        if message.get("internalDate")
                        else headers.get("date")
                    )
                except (ValueError, OverflowError):
                    received = headers.get("date")
                candidates = interview_candidates(
                    headers.get("subject", ""),
                    mime_text(payload),
                    (
                        "https://mail.google.com/mail/u/?authuser="
                        + quote(email, safe="")
                        + "#all/"
                        + m["id"]
                        if email
                        else "https://mail.google.com/mail/u/0/#all/" + m["id"]
                    ),
                    "gmail:" + email + ":" + m["id"] if email else "gmail:" + m["id"],
                    received,
                )
                if store and email:
                    counts = store.gmail_commit(email, m["id"], mode, candidates)
                    for key in counts:
                        totals[key] += counts[key]
                    totals["processed"] += 1
                    known.add(m["id"])
                    store.gmail_progress(
                        email, query, totals["processed"], totals["cached"], mode=mode
                    )
                else:
                    out.extend(candidates)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            if page_token in seen or len(seen) >= 100:
                raise ValueError("Excessive Gmail pagination; narrow GMAIL_QUERY")
            seen.add(page_token)
    if store and email:
        store.gmail_progress(
            email, query, totals["processed"], totals["cached"], "complete", mode=mode
        )
        return totals
    return out
