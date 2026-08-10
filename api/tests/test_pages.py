"""The Page's watermark: uploading one, and what it wins over.

Eight of the ten Pages have no committed asset and publish with nothing stamped
on them, because "commit a PNG under `api/assets/`" is a rule only someone with
the repo can follow. The upload is their route.

Hosting a watermark is what failed in the old system — the bucket was cleared
and every key started returning `NoSuchKey`, and the compositor swallowed it and
printed the page name as text for months. The difference here is that ours
raises, which `test_a_watermark_that_will_not_load_is_an_error` pins.
"""

import io

import pytest
from PIL import Image

from app import media
from app.image import compositor
from app.models import Page


def _transparent_mark() -> bytes:
    """White ink on nothing — the shape a real wordmark has."""
    image = Image.new("RGBA", (400, 120), (255, 255, 255, 0))
    image.paste((255, 255, 255, 255), (10, 10, 390, 110))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_an_uploaded_mark_keeps_its_alpha(client, session, page):
    """Flattened to RGB it is a white wordmark on a white box.

    `upload_inset` converts to RGB and is right to: a disc is cover-cropped over
    the panel and has no transparency to lose. Copying that here would produce a
    mark that looks correct in a file browser and ruins every card.
    """
    response = client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    )

    assert response.status_code == 200, response.text
    stored = response.json()["watermark_upload_path"]
    assert stored, "the row does not point at the upload"

    written = Image.open(io.BytesIO(media.store.read(stored)))
    assert written.mode == "RGBA"
    assert written.getpixel((0, 0))[3] == 0, "the corner was flattened onto white"


def test_the_upload_wins_over_the_committed_asset(client, session, page):
    """Both may be set. The upload is the one that gets drawn."""
    page.watermark_image_path = "assets/watermarks/history-retraced-stacked.png"
    session.add(page)
    session.commit()

    client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    )
    session.refresh(page)

    source = media.watermark_source(
        page.watermark_upload_path, page.watermark_image_path
    )
    assert isinstance(source, bytes), "the committed path was drawn instead"

    # And it is a mark the compositor can actually open, rather than bytes that
    # merely arrived — the old failure was a source that resolved and did not.
    assert compositor._watermark(source, 138) is not None


def test_removing_the_upload_falls_back_to_the_asset(client, session, page):
    page.watermark_image_path = "assets/watermarks/history-retraced-stacked.png"
    session.add(page)
    session.commit()

    client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    )
    removed = client.delete(f"/pages/{page.id}/watermark")

    assert removed.status_code == 200, removed.text
    assert removed.json()["watermark_upload_path"] is None
    session.refresh(page)
    assert (
        media.watermark_source(page.watermark_upload_path, page.watermark_image_path)
        == "assets/watermarks/history-retraced-stacked.png"
    )


def test_replacing_a_mark_drops_the_one_it_supersedes(client, session, page):
    """The bucket's free tier is 1GB and every Page would otherwise keep a pile.

    Safe here in a way a composite is not: the mark is drawn *into* the JPEG, so
    a published card keeps its pixels when the source object goes.
    """
    first = client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    ).json()["watermark_upload_path"]
    second = client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    ).json()["watermark_upload_path"]

    assert first != second
    with pytest.raises(Exception):
        media.store.read(first)
    assert media.store.read(second), "the replacement went with it"


def test_a_page_with_no_mark_gets_its_name_instead_of_nothing(page):
    """The fallback, and the one case the old compositor was right about.

    It is reached only when nothing is configured. A path that will not load
    raises instead — see the module docstring — which is what stops this branch
    from being cover for a mark that has gone missing.
    """
    from app.image import text as overlay
    from app.settings import layout as defaults

    plan = overlay.plan("A hook long enough to fill the panel it is drawn in.", defaults)
    marked = compositor.compose(_hero(), plan, [], None, fallback_text=page.name)
    bare = compositor.compose(_hero(), plan, [], None)

    assert marked != bare, "the name was not drawn"
    assert page.name in compositor.watermark_text_svg(page.name, defaults)
    assert 'text-anchor="end"' in compositor.watermark_text_svg(page.name, defaults)


def test_the_fallback_text_can_be_set_to_something_other_than_the_name(client, page):
    """The name is Metricool's brand name, which is not always printable.

    "GYM Motivation | quotes | videos | tips|" is one of the ten Pages. Stamped
    verbatim on a photograph it is a bar of punctuation.
    """
    saved = client.patch(
        f"/pages/{page.id}", json={"watermark_text": "History Retraced"}
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["watermark_text"] == "History Retraced"

    cleared = client.patch(f"/pages/{page.id}", json={"watermark_text": None})
    assert cleared.json()["watermark_text"] is None, "null clears back to the name"


def _hero() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), (40, 70, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_switching_the_watermark_off_silences_the_text_as_well(client, session, page):
    """Off means a clean photograph, not "no logo but still the name".

    The two are one decision — `Page.watermark()` answers both — because a
    half-off switch that kept printing the page name is the version an operator
    would report as broken.
    """
    page.watermark_image_path = "assets/watermarks/history-retraced-stacked.png"
    session.add(page)
    session.commit()

    assert page.watermark() != (None, None), "on by default"

    off = client.patch(f"/pages/{page.id}", json={"watermark_enabled": False})
    assert off.status_code == 200, off.text
    session.refresh(page)

    assert page.watermark() == (None, None), "the mark or its text survived"


def test_a_file_that_is_not_an_image_is_refused_at_the_upload(client, page):
    """Rather than as a failed composite on the next draft, hours later."""
    response = client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", b"this is not a PNG", "image/png")},
    )

    assert response.status_code == 422
    assert "not an image" in response.json()["detail"]


def test_an_unknown_page_is_a_404_rather_than_a_row_written(client):
    response = client.post(
        "/pages/999/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    )

    assert response.status_code == 404


def test_a_page_serves_the_url_the_browser_fetches(client, session, page):
    """The screen shows the mark it is about to publish with, from the bucket."""
    uploaded = client.post(
        f"/pages/{page.id}/watermark",
        files={"file": ("mark.png", _transparent_mark(), "image/png")},
    ).json()

    assert uploaded["watermark_upload_url"].endswith(uploaded["watermark_upload_path"])
    assert "/object/public/" in uploaded["watermark_upload_url"], "not a signed URL"

    session.refresh(page)
    assert Page.model_validate(page).watermark_upload_url is not None
