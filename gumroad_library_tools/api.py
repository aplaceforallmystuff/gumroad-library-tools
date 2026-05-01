"""Shared helpers for talking to Gumroad's mobile API.

Reads the user's mobile auth token from the running Gumroad iOS-on-Mac app's
NSURLCache (no extra login flow needed — if you've signed into the app, the
token is already on disk).
"""
from __future__ import annotations

import json
import plistlib
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

GUMROAD_BUNDLE_ID = "com.GRD.Gumroad"
API_BASE = "https://api.gumroad.com"


def find_container() -> Path:
    """Find the data container for the Gumroad iOS-on-Mac app.

    iOS-on-Mac apps live under ~/Library/Containers/<UUID>/Data/. The
    container UUID is per-install, so we discover it by reading each
    container's `.com.apple.containermanagerd.metadata.plist` and matching
    on bundle identifier.
    """
    containers_root = Path.home() / "Library/Containers"
    if not containers_root.exists():
        raise FileNotFoundError(f"{containers_root} does not exist")

    for container in containers_root.iterdir():
        if not container.is_dir():
            continue
        meta = container / "Data/.com.apple.containermanagerd.metadata.plist"
        if not meta.exists():
            continue
        try:
            with meta.open("rb") as f:
                d = plistlib.load(f)
        except Exception:
            continue
        if d.get("MCMMetadataIdentifier") == GUMROAD_BUNDLE_ID:
            return container / "Data"

    raise FileNotFoundError(
        f"No container found for {GUMROAD_BUNDLE_ID}. Install the Gumroad app "
        f"from the App Store on Apple Silicon and sign in once."
    )


def cache_db_path(container: Path) -> Path:
    return container / "Library/Caches" / GUMROAD_BUNDLE_ID / "Cache.db"


def read_token(container: Path | None = None) -> str:
    """Read the mobile auth token from any cached API URL.

    The Gumroad app's NSURLCache stores recent API responses keyed by full
    request URL. Every authenticated request includes `?mobile_token=...`,
    so we just walk the cached request keys until we find one.
    """
    container = container or find_container()
    db_path = cache_db_path(container)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Cache.db not found at {db_path}. Open the Gumroad app and load "
            "your library at least once so it caches an authenticated request."
        )

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT request_key FROM cfurl_cache_response").fetchall()
    finally:
        con.close()

    for (key,) in rows:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(key).query)
        tok = params.get("mobile_token", [None])[0]
        if tok:
            return tok

    raise RuntimeError(
        "No mobile_token found in cached requests. Open the Gumroad app and "
        "navigate to your library to populate the cache."
    )


def _api_get(path: str, token: str, params: dict | None = None) -> dict:
    qs = dict(params or {})
    qs["mobile_token"] = token
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(qs)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def list_purchases(token: str, page_size: int = 24) -> Iterator[dict]:
    """Paginate through every purchase in the library."""
    page = 1
    while True:
        data = _api_get(
            "/mobile/purchases/search",
            token,
            params={"items": page_size, "page": page, "archived": "false",
                    "order": "date-desc"},
        )
        purchases = data.get("purchases", [])
        if not purchases:
            return
        for p in purchases:
            yield p
        if len(purchases) < page_size:
            return
        page += 1


def get_product_attributes(token: str, external_id: str) -> dict:
    """Fetch fresh metadata for a single product (file_data list etc)."""
    return _api_get(
        f"/mobile/url_redirects/get_url_redirect_attributes/"
        f"{urllib.parse.quote(external_id, safe='')}",
        token,
    )


def build_download_url(token: str, redirect_token: str, file_id: str) -> str:
    """Build the URL that, when GETed, redirects to a signed S3/CloudFront URL
    serving the original-quality file (NOT the transcoded HLS stream)."""
    qs = urllib.parse.urlencode({"mobile_token": token})
    return (
        f"{API_BASE}/mobile/url_redirects/download/"
        f"{redirect_token}/{urllib.parse.quote(file_id, safe='')}?{qs}"
    )


def get_streaming_playlist(token: str, redirect_token: str, file_id: str) -> str | None:
    """For video files, fetch the HLS playlist URL.

    Lower quality than build_download_url() but works when the original isn't
    available. Returns None if the file isn't streamable.
    """
    data = _api_get(
        f"/mobile/url_redirects/stream/"
        f"{redirect_token}/{urllib.parse.quote(file_id, safe='')}",
        token,
    )
    return data.get("playlist_url") if data.get("success") else None


def human_size(n: float) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def human_duration(seconds: float | None) -> str | None:
    if not seconds:
        return None
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def safe_filename(name: str, max_length: int = 120) -> str:
    """Conservative filename sanitiser — drops anything that's not alphanumeric,
    space, dot, underscore, or hyphen."""
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in name).strip()
    return safe[:max_length] or "untitled"
