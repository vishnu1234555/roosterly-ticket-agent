import httpx
import pytest

from agent.helpdesk import AlreadyHandled, Helpdesk, HelpdeskError


class FakeClock:
    """Time that only moves when the code sleeps, so the tests run instantly."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make(settings, handler):
    clock = FakeClock()
    helpdesk = Helpdesk(settings, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock.clock)
    return helpdesk, clock


def open_list(ids):
    return httpx.Response(200, json={"tickets": [{"id": i} for i in ids], "next_cursor": None})


def test_503_then_200_gives_one_retry(settings):
    answers = iter([503, 200])
    helpdesk, _ = make(settings, lambda request: httpx.Response(next(answers), json={"ok": True}))
    assert helpdesk.status() == {"ok": True}
    assert helpdesk.stats["retries_503"] == 1


def test_429_waits_the_retry_after_time(settings):
    answers = iter([httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={})])
    helpdesk, clock = make(settings, lambda request: next(answers))
    helpdesk.status()
    assert 3.0 in clock.sleeps


def test_409_is_not_retried(settings):
    posts = []

    def handler(request):
        if request.method == "GET":
            return open_list(["T1"])
        posts.append(request)
        return httpx.Response(409, json={"error": "already_handled"})

    helpdesk, _ = make(settings, handler)
    with pytest.raises(AlreadyHandled):
        helpdesk.send("T1", "reply", {})
    assert len(posts) == 1


def test_a_timeout_then_handled_sends_nothing_more(settings):
    still_open, posts = ["T1"], []

    def handler(request):
        if request.method == "GET":
            return open_list(still_open)
        posts.append(request)
        still_open.clear()  # the server saved it...
        raise httpx.ReadTimeout("timed out", request=request)  # ...but the answer never arrived

    helpdesk, _ = make(settings, handler)
    assert helpdesk.send("T1", "reply", {"x": 1}) == "confirmed_after_timeout"
    assert len(posts) == 1


def test_a_timeout_then_still_open_sends_again(settings):
    posts = []

    def handler(request):
        if request.method == "GET":
            return open_list(["T1"] if len(posts) < 2 else [])
        posts.append(request)
        if len(posts) == 1:
            raise httpx.ReadTimeout("timed out", request=request)  # not saved
        return httpx.Response(200, json={"ok": True})

    helpdesk, _ = make(settings, handler)
    assert helpdesk.send("T1", "reply", {"x": 1}) == "sent"
    assert len(posts) == 2


def test_a_handled_ticket_is_skipped(settings):
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(request)
        return open_list([])

    helpdesk, _ = make(settings, handler)
    assert helpdesk.send("T1", "reply", {}) == "skipped_already_handled"
    assert posts == []


def test_paging_follows_next_cursor(settings):
    pages = {None: (["T1", "T2"], "T2"), "T2": (["T3"], None)}

    def handler(request):
        ids, next_cursor = pages[request.url.params.get("cursor")]
        return httpx.Response(200, json={"tickets": [{"id": i} for i in ids], "next_cursor": next_cursor})

    helpdesk, _ = make(settings, handler)
    assert [ticket["id"] for ticket in helpdesk.list_open()] == ["T1", "T2", "T3"]


def test_calls_are_spaced(settings):
    helpdesk, clock = make(settings, lambda request: httpx.Response(200, json={}))
    for _ in range(3):
        helpdesk.status()
    assert clock.sleeps == [0.25, 0.25]


def test_both_headers_are_sent_and_422_is_our_bug(settings):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(422, json={"error": "validation_failed", "problems": ["reason"]})

    helpdesk, _ = make(settings, handler)
    with pytest.raises(HelpdeskError):
        helpdesk.status()
    assert seen["authorization"] == "Bearer test-key"
    assert seen["x-candidate-email"] == "me@example.com"
