"""The circular inset, found by the AI on Unsplash.

No test reaches the network or Gemini: Unsplash is an `httpx.MockTransport`, and
the model is a `FunctionModel`, passed in the same way the writer tests pass one
- or the whole finder is replaced where the test is about its callers.
"""

import io

import httpx
import pytest
from PIL import Image
from pydantic_ai.messages import BinaryImage, ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import generate
from app.image import inset
from app.settings import settings
from app.writer.agent import DraftContent

WRITTEN = DraftContent(
    hook="Semmelweis told doctors to wash their hands in 1847.",
    caption="🧼 They laughed.",
    first_comment="Ignaz Semmelweis (1818-1865).\n\n" + "He was right. " * 80,
    highlight_phrases=["Semmelweis"],
    image_prompt="A 19th-century maternity ward.",
    inset_subject="hand washing",
)


def _photo(pid: str, alt: str, host: str = "images.unsplash.com") -> dict:
    return {
        "id": pid,
        "alt_description": alt,
        "urls": {"small": f"https://{host}/{pid}-small", "regular": f"https://{host}/{pid}-regular"},
        "links": {"download_location": f"https://api.unsplash.com/photos/{pid}/download?ixid=x"},
        "user": {"name": f"Photographer {pid}", "links": {"html": f"https://unsplash.com/@{pid}"}},
    }


RESULTS = [
    _photo("hands", "hands under a running tap"),
    _photo("lab", "a laboratory bench"),
    _photo("plus", "a premium photo", host="plus.unsplash.com"),
]


@pytest.fixture(autouse=True)
def unsplash_key(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", "test-key")


@pytest.fixture
def written(monkeypatch):
    class Result:
        output = WRITTEN

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (120, 90, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _unsplash(results=RESULTS, status=200):
    """A fake Unsplash. Returns the client and every request it saw."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/search/photos":
            return httpx.Response(status, json={"results": results})
        if request.url.host == "api.unsplash.com":
            return httpx.Response(200, json={"url": "tracked"})
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    return httpx.Client(transport=httpx.MockTransport(answer)), seen


def _gemini(subject=None, picks=(1,)):
    """Writes `subject` when asked for a query, then answers `picks` in turn."""
    seen = {"subject_calls": 0, "picks": 0, "pictures": 0}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        if "query" in tool.parameters_json_schema.get("properties", {}):
            seen["subject_calls"] += 1
            return ModelResponse(parts=[ToolCallPart(tool.name, {"query": subject})])
        seen["pictures"] = sum(
            isinstance(item, BinaryImage)
            for message in messages
            for part in message.parts
            if isinstance(getattr(part, "content", None), list)
            for item in part.content
        )
        choice = picks[min(seen["picks"], len(picks) - 1)]
        seen["picks"] += 1
        return ModelResponse(parts=[ToolCallPart(tool.name, {"choice": choice, "reason": "x"})])

    return FunctionModel(respond), seen


def _candidate(pid="hands", host="images.unsplash.com", api="api.unsplash.com") -> inset.Candidate:
    return inset.Candidate(
        title=pid,
        url=f"https://{host}/{pid}-small",
        full_url=f"https://{host}/{pid}-regular",
        download_location=f"https://{api}/photos/{pid}/download",
    )


def _found() -> inset.Found:
    return inset.Found(_png(), "hand washing", _candidate("hands"), [_candidate("hands"), _candidate("lab")])


# --- search ----------------------------------------------------------------------


def test_search_sends_the_key_and_keeps_only_free_photos():
    client, seen = _unsplash()

    found = inset.candidates("hand washing", client)

    assert seen[0].headers["authorization"] == "Client-ID test-key"
    assert seen[0].url.params["content_filter"] == "high"
    assert [c.title for c in found] == ["hands under a running tap", "a laboratory bench"], (
        "the plus.unsplash.com premium photo must be dropped"
    )


def test_no_key_is_an_inset_error_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", "")
    client, seen = _unsplash()

    with pytest.raises(inset.InsetError, match="UNSPLASH_ACCESS_KEY"):
        inset.candidates("hand washing", client)
    assert seen == []


def test_no_key_spends_no_model_call(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", "")
    model, seen = _gemini(subject="hand washing")
    client, requests = _unsplash()

    with pytest.raises(inset.InsetError, match="UNSPLASH_ACCESS_KEY"):
        inset.find_for_post("a post", None, client, model)
    assert seen["subject_calls"] == 0 and requests == []


@pytest.mark.parametrize(("status", "words"), [(401, "access key"), (403, "limit")])
def test_a_refused_key_and_a_spent_rate_limit_say_so(status, words):
    client, _ = _unsplash(status=status)

    with pytest.raises(inset.InsetError, match=words):
        inset.candidates("hand washing", client)


# --- placing ----------------------------------------------------------------------


def test_placing_a_photo_pings_its_download_endpoint():
    client, seen = _unsplash()

    png = inset.place(_candidate("lab"), client)

    assert Image.open(io.BytesIO(png)).format == "PNG"
    urls = [str(r.url) for r in seen]
    assert urls == [
        "https://images.unsplash.com/lab-regular",
        "https://api.unsplash.com/photos/lab/download",
    ]
    assert "authorization" not in seen[0].headers, "the key never goes to the image CDN"


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(host="plus.unsplash.com"),
        _candidate(host="evil.example"),
        _candidate(host="images.unsplash.com.evil.example"),
        _candidate(api="evil.example"),
    ],
)
def test_placing_refuses_anything_but_unsplash_before_a_request(candidate):
    def never(request):
        raise AssertionError(f"requested {request.url}")

    with pytest.raises(inset.InsetError, match="Unsplash"):
        inset.place(candidate, httpx.Client(transport=httpx.MockTransport(never)))


def test_a_failed_download_ping_does_not_lose_the_photo():
    def answer(request):
        if request.url.host == "api.unsplash.com":
            return httpx.Response(503)
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    png = inset.place(_candidate(), httpx.Client(transport=httpx.MockTransport(answer)))

    assert png


# --- the AI's choice ----------------------------------------------------------------


def test_the_model_looks_at_every_candidate_and_its_pick_is_placed():
    model, seen_model = _gemini(picks=(2,))
    client, seen = _unsplash()

    found = inset.find_for_post("a post", "hand washing", client, model)

    assert seen_model["pictures"] == 2, "the model was not shown every candidate"
    assert seen_model["subject_calls"] == 0, "a query was given, so none is asked for"
    assert found.chosen.title == "a laboratory bench"
    downloads = [str(r.url) for r in seen if r.url.path.endswith("/download")]
    assert downloads == ["https://api.unsplash.com/photos/lab/download?ixid=x"], (
        "only the placed photo counts as a download"
    )


def test_without_a_query_the_model_writes_one_from_the_post():
    model, seen = _gemini(subject="hand washing")
    client, requests = _unsplash()

    found = inset.find_for_post("Semmelweis told doctors…", None, client, model)

    assert seen["subject_calls"] == 1
    assert found.subject == "hand washing"
    assert requests[0].url.params["query"] == "hand washing"


def test_nothing_to_photograph_is_an_inset_error_and_nothing_is_searched():
    model, seen = _gemini(subject=None)
    client, requests = _unsplash()

    with pytest.raises(inset.InsetError, match="photographed"):
        inset.find_for_post("an abstract idea", None, client, model)
    assert requests == [] and seen["picks"] == 0


def test_none_fitting_is_an_inset_error_naming_the_query():
    model, _ = _gemini(picks=(None,))
    client, requests = _unsplash()

    with pytest.raises(inset.InsetError, match="hand washing"):
        inset.find_for_post("a post", "hand washing", client, model)
    assert not any(r.url.path.endswith("/download") for r in requests)


def test_an_out_of_range_pick_is_retried_never_returned():
    model, seen = _gemini(picks=(7, 1))
    client, _ = _unsplash()

    found = inset.find_for_post("a post", "hand washing", client, model)

    assert seen["picks"] == 2
    assert found.chosen.title == "hands under a running tap"


def test_no_results_asks_the_model_nothing():
    model, seen = _gemini()
    client, _ = _unsplash(results=[])

    with pytest.raises(inset.InsetError, match="no Unsplash photos"):
        inset.find_for_post("a post", "hand washing", client, model)
    assert seen["picks"] == 0


# --- the run ----------------------------------------------------------------------


def test_a_run_asked_to_find_an_inset_uses_the_writers_query(
    client, written, illustrated, monkeypatch
):
    asked = []
    monkeypatch.setattr(
        inset, "find_for_post", lambda post, subject=None: asked.append((post, subject)) or _found()
    )

    client.post("/generate", json={"page_ids": [1], "topic": "x", "find_inset": True})
    draft = client.get("/drafts/1").json()

    assert asked[0][1] == "hand washing", "the writer's query saves a model call"
    assert "Semmelweis told doctors" in asked[0][0]
    assert draft["inset_image_path"] and draft["composed_image_path"]
    assert draft["status"] == "review"


@pytest.mark.parametrize("failure", [inset.InsetError("nothing fits"), RuntimeError("503")])
def test_a_miss_or_an_outage_is_a_warning_and_the_draft_still_arrives(
    client, written, illustrated, monkeypatch, failure
):
    def fail(*a, **k):
        raise failure

    monkeypatch.setattr(inset, "find_for_post", fail)

    client.post("/generate", json={"page_ids": [1], "topic": "x", "find_inset": True})
    draft = client.get("/drafts/1").json()

    assert draft["status"] == "review"
    assert draft["composed_image_path"], "the card is still drawn without the circle"
    assert draft["inset_image_path"] is None
    assert any("no inset" in w for w in draft["warnings"])


def test_without_the_flag_nothing_is_looked_up(client, written, illustrated, monkeypatch):
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("not asked for"))

    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    assert client.get("/drafts/1").json()["inset_image_path"] is None


def test_no_image_wins_over_find_inset(client, written, monkeypatch):
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("no card to circle"))

    client.post(
        "/generate",
        json={"page_ids": [1], "topic": "x", "no_image": True, "find_inset": True},
    )

    assert client.get("/drafts/1").json()["find_inset"] is False


# --- the drawer's button ------------------------------------------------------------


def test_find_with_ai_reads_the_saved_post_and_returns_what_it_chose_among(
    client, written, illustrated, monkeypatch
):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    asked = []
    monkeypatch.setattr(
        inset, "find_for_post", lambda post, subject=None: asked.append((post, subject)) or _found()
    )

    response = client.post("/drafts/1/inset/find", json={})

    assert response.status_code == 200, response.text
    assert asked[0][1] is None, "the drawer re-reads the post rather than trusting a stored query"
    assert "Semmelweis told doctors" in asked[0][0]
    body = response.json()
    assert body["chosen"]["title"] == "hands"
    assert len(body["candidates"]) == 2
    assert client.get("/drafts/1").json()["inset_image_path"]


def test_a_swap_places_that_photo_and_asks_no_model(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    placed = []
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("a swap asked the AI"))
    monkeypatch.setattr(inset, "place", lambda candidate, *a: placed.append(candidate.title) or _png())

    response = client.post("/drafts/1/inset/find", json={"candidate": _candidate("lab").model_dump()})

    assert response.status_code == 200, response.text
    assert placed == ["lab"]
    assert client.get("/drafts/1").json()["inset_image_path"]


def test_a_swap_off_unsplash_is_a_422(client, written, illustrated):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    response = client.post(
        "/drafts/1/inset/find", json={"candidate": _candidate(host="evil.example").model_dump()}
    )

    assert response.status_code == 422
    assert client.get("/drafts/1").json()["inset_image_path"] is None


def test_no_photo_is_a_404_and_a_dead_model_is_a_502(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    def miss(*a, **k):
        raise inset.InsetError("none of the Unsplash photos for “hand washing” fit the post")

    monkeypatch.setattr(inset, "find_for_post", miss)
    response = client.post("/drafts/1/inset/find", json={})
    assert response.status_code == 404
    assert "hand washing" in response.json()["detail"]

    def outage(*a, **k):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(inset, "find_for_post", outage)
    assert client.post("/drafts/1/inset/find", json={}).status_code == 502


# --- Manual, written by hand ----------------------------------------------------------


def test_a_hand_written_draft_can_ask_the_ai_for_an_inset(client, monkeypatch):
    asked = []
    monkeypatch.setattr(
        inset, "find_for_post", lambda post, subject=None: asked.append((post, subject)) or _found()
    )

    response = client.post(
        "/drafts/manual",
        data={"page_id": "1", "hook": "Semmelweis told doctors to wash.", "find_inset": "true"},
    )

    assert response.status_code == 201, response.text
    assert asked == [("Semmelweis told doctors to wash.", None)]
    assert response.json()["inset_image_path"]


def test_a_hand_written_draft_asks_no_model_by_default(client, monkeypatch):
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("not asked for"))

    response = client.post("/drafts/manual", data={"page_id": "1", "hook": "Anything."})

    assert response.status_code == 201
