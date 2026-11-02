import asyncio
import base64
import httpx
import pytest
from meridian.connectors import pages, mime_text, gmail_sync, canvas_sync, gmail_get
from meridian.extract import extract_ai


@pytest.mark.parametrize("status,reason", [(403, "rateLimitExceeded"), (403, "userRateLimitExceeded"), (429, None)])
def test_gmail_quota_retry_preserves_request(monkeypatch, status, reason):
    requests, delays = [], []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("meridian.connectors.asyncio.sleep", sleep)

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(status, json={"error": {"errors": [{"reason": reason}]}}, headers={"Retry-After": "12"})
        return httpx.Response(200, json={"messages": [{"id": "retained"}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await gmail_get(client, "https://gmail.googleapis.com/messages", {"pageToken": "next"})

    assert asyncio.run(run()).json()["messages"][0]["id"] == "retained"
    assert delays == [12]
    assert [request.url.params["pageToken"] for request in requests] == ["next", "next"]


def test_gmail_permission_failure_does_not_retry(monkeypatch):
    async def sleep(delay):
        pytest.fail("Permission failures must not retry")

    monkeypatch.setattr("meridian.connectors.asyncio.sleep", sleep)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(403, json={"error": {"errors": [{"reason": "insufficientPermissions"}]}}))) as client:
            await gmail_get(client, "https://gmail.googleapis.com/messages")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())


def test_gmail_quota_retries_are_bounded(monkeypatch):
    requests, delays = [], []

    async def sleep(delay):
        delays.append(delay)

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "3600"})

    monkeypatch.setattr("meridian.connectors.asyncio.sleep", sleep)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await gmail_get(client, "https://gmail.googleapis.com/messages")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
    assert len(requests) == 8
    assert delays == [60] * 7


def test_pagination_and_cross_origin_guard():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json=[1],
                headers={"Link": '<https://canvas.example/items?page=2>; rel="next"'},
            )
        return httpx.Response(200, json=[2])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return [x async for x in pages(c, "https://canvas.example/items")]

    assert asyncio.run(run()) == [[1], [2]]

    def malicious(req):
        return httpx.Response(
            200, json=[], headers={"Link": '<https://evil.example/items>; rel="next"'}
        )

    async def bad():
        async with httpx.AsyncClient(transport=httpx.MockTransport(malicious)) as c:
            return [x async for x in pages(c, "https://canvas.example/items")]

    with pytest.raises(ValueError, match="cross-origin"):
        asyncio.run(bad())


def test_gmail_mime_prefers_plain_text():
    def part(mime, text):
        return {
            "mimeType": mime,
            "body": {
                "data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
            },
        }

    payload = {
        "parts": [
            part("text/plain", "Interview due tomorrow"),
            part("text/html", "<p>Duplicate</p>"),
        ]
    }
    assert mime_text(payload) == "Interview due tomorrow"


def test_gmail_lists_then_fetches_full_messages(monkeypatch):
    monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
    for k in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
        "MERIDIAN_AI",
    ):
        monkeypatch.delenv(k, raising=False)
    requests = []

    def handler(req):
        requests.append(req)
        assert req.headers["Authorization"] == "Bearer test-token"
        if req.url.path.endswith("/messages"):
            if req.url.params.get("pageToken") == "next":
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(
                200, json={"messages": [{"id": "abc"}], "nextPageToken": "next"}
            )
        return httpx.Response(
            200,
            json={
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Subject", "value": "Interview invitation"}],
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"Please complete your interview by 2026-11-04 12:00"
                        ).decode()
                    },
                }
            },
        )

    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.connectors.httpx.AsyncClient",
        lambda **kw: cls(transport=httpx.MockTransport(handler), **kw),
    )
    items = asyncio.run(gmail_sync())
    assert len(requests) == 3
    assert any(t.category == "career" and t.due_at for t in items)
    assert requests[1].url.params["format"] == "full"


def test_canvas_syllabus_assignment_and_gradescope(monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "test-token")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.example")
    monkeypatch.delenv("MERIDIAN_AI", raising=False)

    def handler(req):
        p = req.url.path
        if p.endswith("/courses"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "course_code": "CS 2800",
                        "syllabus_body": "<p>Quiz next week</p>",
                    }
                ],
            )
        if p.endswith("/assignments"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 2,
                        "name": "Homework",
                        "due_at": "2026-11-04T23:59:00Z",
                        "description": "Submit on Gradescope",
                        "submission": {"workflow_state": "submitted"},
                    }
                ],
            )
        return httpx.Response(200, json=[])

    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.connectors.httpx.AsyncClient",
        lambda **kw: cls(transport=httpx.MockTransport(handler), **kw),
    )
    items = asyncio.run(canvas_sync())
    assert len(items) == 2
    assert items[0].confidence == "review" and items[0].source_type == "syllabus"
    assert items[1].destination == "Gradescope"


def test_ai_rejects_invented_evidence_and_keeps_review(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")

    def handler(req):
        import json

        body = json.loads(req.content)
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        data = {
            "items": [
                {
                    "title": "HW",
                    "due_at": "2026-11-04T23:59:00Z",
                    "evidence": "Homework due tomorrow",
                    "category": "academic",
                    "destination": "Canvas",
                },
                {
                    "title": "Invented",
                    "due_at": None,
                    "evidence": "This does not exist",
                    "category": "academic",
                    "destination": "Canvas",
                },
            ]
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {"content": [{"type": "output_text", "text": json.dumps(data)}]}
                ]
            },
        )

    cls = httpx.AsyncClient
    monkeypatch.setattr(
        "meridian.extract.httpx.AsyncClient",
        lambda **kw: cls(transport=httpx.MockTransport(handler), **kw),
    )
    items = asyncio.run(extract_ai("Homework due tomorrow", "CS", "syllabus"))
    assert len(items) == 1 and items[0].confidence == "review"
