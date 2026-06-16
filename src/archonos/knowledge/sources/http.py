"""HTTP helpers for paper-source modules.

Centralized so every source uses the same User-Agent, timeout, error
handling, and JSON/XML parsing. No third-party deps — urllib + json +
xml.etree only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

# Single User-Agent across the kernel. Real email for Unpaywall's polite
# pool is appended at call time there.
DEFAULT_UA = "archonos-next/0.1 (kernel; +https://github.com/alfredaranas/archonos-next)"
DEFAULT_TIMEOUT = 30  # seconds


class HTTPError(Exception):
    """Wraps urllib errors with a useful message."""

    def __init__(self, url: str, status: int | None, body: str = ""):
        self.url = url
        self.status = status
        self.body = body[:200]
        msg = f"HTTP {status} for {url}" if status else f"Network error for {url}"
        if body:
            msg += f" (body: {body[:200]!r})"
        super().__init__(msg)


def get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_UA,
) -> bytes:
    """GET a URL. Returns body bytes. Raises HTTPError on non-2xx."""
    h = {"User-Agent": user_agent, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise HTTPError(url, e.code, body) from e
    except urllib.error.URLError as e:
        raise HTTPError(url, None, str(e)) from e


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_UA,
) -> Any:
    """GET a URL and parse as JSON. If `params` is given, URL-encode them."""
    if params:
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None},
            doseq=True,
        )
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    body = get(url, headers=headers, timeout=timeout, user_agent=user_agent)
    return json.loads(body.decode("utf-8", errors="replace"))


def get_xml(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_UA,
) -> ET.Element:
    """GET a URL and parse as XML. Returns root Element."""
    if params:
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None},
            doseq=True,
        )
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    body = get(url, headers=headers, timeout=timeout, user_agent=user_agent)
    return ET.fromstring(body)


def ns_strip(tag: str) -> str:
    """Strip XML namespace from a tag like '{http://...}entry' -> 'entry'."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
