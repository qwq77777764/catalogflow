import socket

import pytest

from catalogflow.media import validate_public_https_url


def test_image_url_rejects_private_network(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(ValueError, match="non-public"):
        validate_public_https_url("https://images.example/product.jpg")


def test_image_url_accepts_public_https(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )

    validate_public_https_url("https://images.example/product.jpg")
