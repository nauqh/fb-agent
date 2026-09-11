"""The shared-client cache: same shape, same client."""

import httpx

from app.http import shared


def test_the_same_shape_reuses_one_client():
    assert shared(30.0, follow_redirects=True) is shared(30.0, follow_redirects=True)


def test_a_different_shape_is_a_different_client():
    assert shared(30.0) is not shared(60.0)
    assert shared(30.0) is not shared(30.0, follow_redirects=True)


def test_the_timeout_travels():
    client = shared(30.0)
    assert isinstance(client, httpx.Client)
    assert client.timeout.connect == 30.0
