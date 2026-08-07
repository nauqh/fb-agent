"""The hero's ladder: retry while unavailable, step down, stop on anything else.

The distinction under test is the one the code got wrong: a **refusal** is
answered and billed, an **outage** is neither. Retrying the first spends money to
be told no twice; not retrying the second throws away a run for free.
"""

from types import SimpleNamespace

import pytest

from app.image import hero
from app.settings import settings

REAL_GENERATE = hero.generate
"""Captured at import, before `conftest.never_buy_an_image` replaces it.

That fixture is autouse and exists so no test can quietly bill Google. These
tests need the real function with a fake transport underneath it, which is the
one case the blanket ban cannot express.
"""

UNAVAILABLE = (
    "ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model "
    "is currently experiencing high demand.', 'status': 'UNAVAILABLE'}}"
)


def _drawn(data: bytes = b"png-bytes"):
    """A response with an image in it, shaped like the SDK's."""
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data))
    content = SimpleNamespace(parts=[part])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def _refused():
    """A refusal: well-formed, no parts, and charged for."""
    content = SimpleNamespace(parts=[])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[str] = []
        self.sent: list[tuple[str, object]] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        self.sent.append((contents, config))
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def transport(monkeypatch):
    """Swap the SDK client for a script of outcomes, and take the sleeping out.

    `_backoff` returning zero keeps the suite fast without pretending the waits
    are not there — the retry count is what these tests are about.
    """
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_image_model", "primary-image")
    monkeypatch.setattr(settings, "gemini_image_fallback_models", "backup-image")
    monkeypatch.setattr(hero, "_backoff", lambda attempt: 0.0)

    def install(*script):
        models = FakeModels(script)
        monkeypatch.setattr(
            hero.genai, "Client", lambda **_kwargs: SimpleNamespace(models=models)
        )
        return models

    return install


def test_an_outage_is_retried_on_the_same_model(transport):
    """503 means nothing was generated, so nothing was billed. Asking again is free."""
    models = transport(RuntimeError(UNAVAILABLE), _drawn())

    result = REAL_GENERATE("a ship", 800)

    assert result.data == b"png-bytes"
    assert models.calls == ["primary-image", "primary-image"], "it must not skip to the backup"
    assert result.model == "primary-image"


def test_the_backup_model_takes_over_when_the_first_stays_down(transport):
    models = transport(*[RuntimeError(UNAVAILABLE)] * hero.ATTEMPTS_PER_MODEL, _drawn())

    result = REAL_GENERATE("a ship", 800)

    assert models.calls == ["primary-image"] * hero.ATTEMPTS_PER_MODEL + ["backup-image"]
    assert result.model == "backup-image", "the caller has to be able to tell"


def test_a_refusal_stops_everything_immediately(transport):
    """The expensive mistake this guards.

    A refusal is a completed, billed call. Retrying it three times and then
    asking a second model buys four identical rejections of the same prompt.
    """
    models = transport(_refused(), _drawn())

    with pytest.raises(hero.HeroError, match="no image"):
        REAL_GENERATE("a photo of a named living person", 800)

    assert models.calls == ["primary-image"], "a refusal must cost exactly one call"


@pytest.mark.parametrize(
    "message",
    [
        "ClientError: 400 INVALID_ARGUMENT",
        "ClientError: 404 NOT_FOUND. this model is no longer available",
        "API key not valid",
    ],
)
def test_a_broken_request_is_not_retried(transport, message):
    """404 is how a pinned fallback rots, and it must surface rather than be spent."""
    models = transport(RuntimeError(message), _drawn())

    with pytest.raises(hero.HeroError):
        REAL_GENERATE("a ship", 800)

    assert models.calls == ["primary-image"]


def test_the_whole_chain_being_down_says_so(transport):
    every_call = [RuntimeError(UNAVAILABLE)] * (hero.ATTEMPTS_PER_MODEL * 2)
    transport(*every_call)

    with pytest.raises(hero.HeroError, match="every image model was unavailable") as caught:
        REAL_GENERATE("a ship", 800)

    assert "primary-image, backup-image" in str(caught.value), "name what was tried"


def test_no_fallback_configured_means_the_one_model(transport, monkeypatch):
    monkeypatch.setattr(settings, "gemini_image_fallback_models", "")
    models = transport(*[RuntimeError(UNAVAILABLE)] * hero.ATTEMPTS_PER_MODEL)

    with pytest.raises(hero.HeroError):
        REAL_GENERATE("a ship", 800)

    assert models.calls == ["primary-image"] * hero.ATTEMPTS_PER_MODEL


def test_the_chain_never_lists_the_same_model_twice(monkeypatch):
    """Otherwise a copy-pasted .env pays for the same outage twice over."""
    monkeypatch.setattr(settings, "gemini_image_model", "primary-image")
    monkeypatch.setattr(
        settings, "gemini_image_fallback_models", " primary-image , backup-image ,, "
    )

    assert settings.image_fallback_chain == ("primary-image", "backup-image")


def test_the_brand_photography_rules_are_sent_with_every_hero(transport):
    """The bug this guards shipped, silently, for the life of the repo.

    `generate` took only the writer's one-line subject and sent exactly that, so
    every hero was ordered without photorealism, without the mid-shot rule,
    without the "keep the top-right clear" instruction the watermark depends on,
    and without the exclusions — `prompts.image_prompt()` had no callers at all.
    Nothing failed; the pictures were just quietly off-brand, which is the kind
    of defect a comparison against the old system would have blamed on the model.
    """
    models = transport(_drawn())

    REAL_GENERATE("A woman at a drafting table.", 800)

    [(contents, config)] = models.sent
    assert "photorealistic" in config.system_instruction.lower(), (
        "the style block from prompts/image.txt was not sent"
    )
    assert "top-right" in config.system_instruction, "nor the rule the watermark needs"
    assert "A woman at a drafting table." in contents, "the subject still leads"
    assert "ZERO readable text" in contents, "the no-text reminder rides on the prompt"


def test_the_panel_share_in_the_prompt_comes_from_the_layout(transport):
    """`{panel_pct}` is substituted, not sent as a literal brace.

    The old system hardcoded this number in the prompt and rendered a different
    one, which is exactly the drift `prompts._tokens` exists to stop.
    """
    from app.settings import layout

    models = transport(_drawn())

    REAL_GENERATE("a ship", 800)

    [(_, config)] = models.sent
    assert "{panel_pct}" not in config.system_instruction
    assert f"~{round(layout.panel.ratio * 100)}%" in config.system_instruction


def test_a_missing_key_fails_before_any_call(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(hero.HeroError, match="GEMINI_API_KEY"):
        REAL_GENERATE("a ship", 800)
