"""Bounded download of operator-authorized public product images."""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def validate_public_https_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("image URLs must be credential-free HTTPS URLs")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("image hostname did not resolve") from exc
    if not addresses:
        raise ValueError("image hostname did not resolve")
    for address in addresses:
        value = address[4][0].split("%", 1)[0]
        if not ipaddress.ip_address(value).is_global:
            raise ValueError("image URL resolved to a non-public network")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        validate_public_https_url(new_url)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def materialize_authorized_images(urls: tuple[str, ...], directory: str | Path) -> list[Path]:
    """Download a small public image set into a temporary, neutral-named directory."""

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    results: list[Path] = []
    for index, url in enumerate(dict.fromkeys(urls), start=1):
        if len(results) >= MAX_IMAGES:
            break
        validate_public_https_url(url)
        request = urllib.request.Request(  # noqa: S310 - URL is HTTPS and public-host validated
            url,
            headers={"User-Agent": "CatalogFlow/0.2 image input"},
        )
        with opener.open(request, timeout=30) as response:  # noqa: S310 - validated HTTPS
            content_type = response.headers.get_content_type().lower()
            extension = _EXTENSIONS.get(content_type)
            if not extension:
                raise ValueError(f"unsupported image content type: {content_type}")
            declared_size = int(response.headers.get("Content-Length", "0") or 0)
            if declared_size > MAX_IMAGE_BYTES:
                raise ValueError("image exceeds the 8 MiB limit")
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("image exceeds the 8 MiB limit")
        path = destination / f"{index:04d}{extension}"
        path.write_bytes(data)
        results.append(path)
    return results
