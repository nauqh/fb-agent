"""The circular inset, found by the AI on Google Images through SerpAPI.

No test reaches the network or Gemini: SerpAPI is an `httpx.MockTransport`, and
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


def _row(title: str, source="Britannica", width=1200, product=False, original=None) -> dict:
    """One `images_results` row, as the google_images engine returns it."""
    slug = title.replace(" ", "_")
    return {
        "title": title,
        "source": source,
        "is_product": product,
        "original_width": width,
        "original_height": width,
        "thumbnail": f"https://encrypted-tbn0.gstatic.com/{slug}-thumb.jpg",
        "original": original or f"https://cdn.example/{slug}-full.jpg",
    }


# Google's own ranking, filters and all: the shop listing, the watermarked
# stock preview and the listing-sized thumbnail all rank above the real picture.
RESULTS = [
    _row("a mug of him", product=True),
    _row("a watermarked print", source="Getty Images"),
    _row("a listing thumbnail", width=200),
    _row("an insecure host", original="http://cdn.example/x.jpg"),
    _row("hands under a running tap"),
    _row("a laboratory bench", source="PBS"),
]


@pytest.fixture(autouse=True)
def serp_key(monkeypatch):
    monkeypatch.setattr(settings, "serp_api_key", "test-key")


@pytest.fixture
def written(monkeypatch):
    class Result:
        output = WRITTEN

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (120, 90, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _serpapi(results=RESULTS, status=200, body=None):
    """A fake SerpAPI. Returns the client and every request it saw."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/search.json":
            return httpx.Response(status, json=body or {"images_results": results})
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


def _candidate(pid="hands", host="cdn.example") -> inset.Candidate:
    return inset.Candidate(
        title=pid,
        url=f"https://encrypted-tbn0.gstatic.com/{pid}-thumb.jpg",
        full_url=f"https://{host}/{pid}-full.jpg",
        source="Britannica",
    )


def _found() -> inset.Found:
    return inset.Found(_png(), "hand washing", _candidate("hands"), [_candidate("hands"), _candidate("lab")])


# --- search ----------------------------------------------------------------------


def test_search_sends_the_key_and_drops_what_google_ranks_above_the_picture():
    client, seen = _serpapi()

    found = inset.candidates("hand washing", client)

    assert seen[0].url.params["api_key"] == "test-key"
    assert seen[0].url.params["safe"] == "active"
    assert [c.title for c in found] == ["hands under a running tap", "a laboratory bench"], (
        "the shop listing, the stock watermark, the 200px thumbnail and the "
        "http original all have to go"
    )
    assert found[1].source == "PBS", "who published it travels with the picture"


def test_no_key_is_an_inset_error_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "serp_api_key", "")
    client, seen = _serpapi()

    with pytest.raises(inset.InsetError, match="SERP_API_KEY"):
        inset.candidates("hand washing", client)
    assert seen == []


def test_no_key_spends_no_model_call(monkeypatch):
    monkeypatch.setattr(settings, "serp_api_key", "")
    model, seen = _gemini(subject="hand washing")
    client, requests = _serpapi()

    with pytest.raises(inset.InsetError, match="SERP_API_KEY"):
        inset.find_for_post("a post", None, client, model)
    assert seen["subject_calls"] == 0 and requests == []


@pytest.mark.parametrize(("status", "words"), [(401, "refused the key"), (429, "used up")])
def test_a_refused_key_and_a_spent_plan_say_so(status, words):
    client, _ = _serpapi(status=status)

    with pytest.raises(inset.InsetError, match=words):
        inset.candidates("hand washing", client)


def test_an_error_inside_a_200_is_still_an_error():
    """SerpAPI answers 200 with an `error` field for a search that found nothing."""
    client, _ = _serpapi(body={"error": "Google has not returned any results"})

    with pytest.raises(inset.InsetError, match="not returned any results"):
        inset.candidates("qwxzzy", client)


# --- placing ----------------------------------------------------------------------


def test_placing_fetches_the_publishers_own_image_as_png():
    client, seen = _serpapi()

    png = inset.place(_candidate("lab"), client)

    assert Image.open(io.BytesIO(png)).format == "PNG"
    assert [str(r.url) for r in seen] == ["https://cdn.example/lab-full.jpg"]


def test_a_hotlink_blocked_original_falls_back_to_googles_thumbnail():
    """Common enough that losing the picture over it would be the failure the
    operator sees most."""

    def answer(request):
        if request.url.host == "cdn.example":
            return httpx.Response(403)
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    client = httpx.Client(transport=httpx.MockTransport(answer))

    assert inset.place(_candidate(), client)


@pytest.mark.parametrize(
    "url",
    ["http://cdn.example/x.jpg", "https://localhost/x.jpg", "https://127.0.0.1/x.jpg"],
)
def test_placing_refuses_a_private_or_plain_http_address(url):
    """`full_url` arrives from the browser on a swap, so this is the only check."""

    def never(request):
        raise AssertionError(f"requested {request.url}")

    candidate = _candidate().model_copy(update={"full_url": url, "url": url})
    with pytest.raises(inset.InsetError, match="public https"):
        inset.place(candidate, httpx.Client(transport=httpx.MockTransport(never)))


# --- the AI's choice ----------------------------------------------------------------


def test_the_model_looks_at_every_candidate_and_its_pick_is_placed():
    model, seen_model = _gemini(picks=(2,))
    client, seen = _serpapi()

    found = inset.find_for_post("a post", "hand washing", client, model)

    assert seen_model["pictures"] == 2, "the model was not shown every candidate"
    assert seen_model["subject_calls"] == 0, "a query was given, so none is asked for"
    assert found.chosen.title == "a laboratory bench"
    large = [str(r.url) for r in seen if r.url.host == "cdn.example"]
    assert large == ["https://cdn.example/a_laboratory_bench-full.jpg"], (
        "only the chosen image is fetched at full size"
    )


def test_without_a_query_the_model_writes_one_from_the_post():
    model, seen = _gemini(subject="hand washing")
    client, requests = _serpapi()

    found = inset.find_for_post("Semmelweis told doctors…", None, client, model)

    assert seen["subject_calls"] == 1
    assert found.subject == "hand washing"
    assert requests[0].url.params["q"] == "hand washing"


def test_nothing_to_photograph_is_an_inset_error_and_nothing_is_searched():
    model, seen = _gemini(subject=None)
    client, requests = _serpapi()

    with pytest.raises(inset.InsetError, match="photographed"):
        inset.find_for_post("an abstract idea", None, client, model)
    assert requests == [] and seen["picks"] == 0


def test_none_fitting_is_an_inset_error_naming_the_query():
    model, _ = _gemini(picks=(None,))
    client, requests = _serpapi()

    with pytest.raises(inset.InsetError, match="hand washing") as caught:
        inset.find_for_post("a post", "hand washing", client, model)
    assert not any(r.url.host == "cdn.example" for r in requests)
    assert [c.title for c in caught.value.candidates] == [
        "hands under a running tap",
        "a laboratory bench",
    ], "the photos it looked at travel with the refusal"


def test_an_out_of_range_pick_is_retried_never_returned():
    model, seen = _gemini(picks=(7, 1))
    client, _ = _serpapi()

    found = inset.find_for_post("a post", "hand washing", client, model)

    assert seen["picks"] == 2
    assert found.chosen.title == "hands under a running tap"


def test_no_results_asks_the_model_nothing():
    model, seen = _gemini()
    client, _ = _serpapi(results=[])

    with pytest.raises(inset.InsetError, match="no Google images"):
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
    assert [c["title"] for c in draft["inset_candidates"]] == ["hands", "lab"], (
        "a run keeps its alternatives, so Review opens on them"
    )
    assert draft["inset_photo_url"] == _candidate("hands").url
    assert draft["status"] == "review"


def test_a_run_where_nothing_fits_still_keeps_the_photos(
    client, written, illustrated, monkeypatch
):
    def none_fit(*a, **k):
        raise inset.InsetError("none fit", [_candidate("hands"), _candidate("lab")])

    monkeypatch.setattr(inset, "find_for_post", none_fit)

    client.post("/generate", json={"page_ids": [1], "topic": "x", "find_inset": True})
    draft = client.get("/drafts/1").json()

    assert draft["inset_image_path"] is None
    assert draft["inset_photo_url"] is None
    assert [c["title"] for c in draft["inset_candidates"]] == ["hands", "lab"]


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
    assert body["inset_image_path"]
    assert body["inset_photo_url"] == _candidate("hands").url
    assert [c["title"] for c in body["inset_candidates"]] == ["hands", "lab"]


def test_a_swap_places_that_photo_and_asks_no_model(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    placed = []
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("a swap asked the AI"))
    monkeypatch.setattr(inset, "place", lambda candidate, *a: placed.append(candidate.title) or _png())

    response = client.post("/drafts/1/inset/find", json={"candidate": _candidate("lab").model_dump()})

    assert response.status_code == 200, response.text
    assert placed == ["lab"]
    assert response.json()["inset_image_path"]
    assert response.json()["inset_photo_url"] == _candidate("lab").url


def test_a_swap_off_the_public_web_is_a_422(client, written, illustrated):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    response = client.post(
        "/drafts/1/inset/find", json={"candidate": _candidate(host="evil.example").model_dump()}
    )

    assert response.status_code == 422
    assert client.get("/drafts/1").json()["inset_image_path"] is None


def test_no_photo_is_a_404_and_a_dead_model_is_a_502(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    def miss(*a, **k):
        raise inset.InsetError(
            "none of the Google images for “hand washing” fit the post",
            [_candidate("lab")],
        )

    monkeypatch.setattr(inset, "find_for_post", miss)
    response = client.post("/drafts/1/inset/find", json={})
    assert response.status_code == 404
    assert "hand washing" in response.json()["detail"]
    assert [c["title"] for c in client.get("/drafts/1").json()["inset_candidates"]] == ["lab"], (
        "a 404 for 'none fit' still commits the photos it looked at"
    )

    def outage(*a, **k):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(inset, "find_for_post", outage)
    assert client.post("/drafts/1/inset/find", json={}).status_code == 502


def test_an_upload_is_not_one_of_the_offered_photos_but_they_stay(
    client, written, illustrated, a_photograph, monkeypatch
):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: _found())
    client.post("/drafts/1/inset/find", json={})

    response = client.post("/drafts/1/inset", files={"file": ("mine.png", a_photograph, "image/png")})

    assert response.status_code == 200, response.text
    assert response.json()["inset_photo_url"] is None
    assert len(response.json()["inset_candidates"]) == 2


# --- the drawer's keyword search ------------------------------------------------------


def test_a_keyword_search_offers_photos_and_places_nothing(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    searched = []
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: pytest.fail("a search asked the AI"))
    monkeypatch.setattr(
        inset,
        "candidates",
        lambda query, *a: searched.append(query) or [_candidate("lab"), _candidate("hands")],
    )

    response = client.post("/drafts/1/inset/search", json={"query": "  hand washing  "})

    assert response.status_code == 200, response.text
    assert searched == ["hand washing"]
    body = response.json()
    assert [c["title"] for c in body["inset_candidates"]] == ["lab", "hands"]
    assert body["inset_subject"] == "hand washing", "the box reopens on the operator's query"
    assert body["inset_image_path"] is None and body["inset_photo_url"] is None


def test_a_search_with_no_results_is_a_404_and_keeps_the_old_offers(
    client, written, illustrated, monkeypatch
):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    monkeypatch.setattr(inset, "find_for_post", lambda *a, **k: _found())
    client.post("/drafts/1/inset/find", json={})
    monkeypatch.setattr(inset, "candidates", lambda *a: [])

    response = client.post("/drafts/1/inset/search", json={"query": "qwxzzy"})

    assert response.status_code == 404
    assert "qwxzzy" in response.json()["detail"]
    assert len(client.get("/drafts/1").json()["inset_candidates"]) == 2


def test_a_search_serpapi_refuses_is_a_502(client, written, illustrated, monkeypatch):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    def refused(*a, **k):
        raise inset.InsetError("SerpAPI answered 503")

    monkeypatch.setattr(inset, "candidates", refused)

    response = client.post("/drafts/1/inset/search", json={"query": "hand washing"})

    assert response.status_code == 502
    assert "503" in response.json()["detail"]


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
