"""
api/instagram.py — Instagram public data fetcher with robust async handling.
Fetches profile and post info without API keys.
All calls have strict timeouts so the bot never freezes.
"""

import asyncio
import aiohttp
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_TIMEOUT  = aiohttp.ClientTimeout(total=12, connect=5)
_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}
_API_HEADERS = {
    **_HEADERS,
    "X-IG-App-ID":    "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "x-asbd-id":      "198387",
    "x-ig-www-claim": "0",
}


# ─── Text utilities ──────────────────────────────────────────────────────────

def clean_username(text: str) -> str:
    """Extract bare username from URL, @handle, or plain text."""
    text = text.strip()
    if "instagram.com" in text:
        m = re.search(r"instagram\.com/([^/?#\s]+)", text)
        if m:
            text = m.group(1)
    return text.lstrip("@").rstrip("/")


def is_post_url(text: str) -> bool:
    """True if text looks like an Instagram post / reel / TV URL."""
    return bool(re.search(r"instagram\.com/(p|reel|tv)/", text, re.I))


def extract_shortcode(url: str) -> Optional[str]:
    """Extract the shortcode from an Instagram post/reel URL."""
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url, re.I)
    return m.group(1) if m else None


def _fmt(n: Optional[int]) -> str:
    """Format a large number to a readable string."""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)

# public alias used by withdraw.py
_fmt_count = _fmt


# ─── Profile fetcher ─────────────────────────────────────────────────────────

async def fetch_profile_info(username: str) -> dict:
    """
    Fetch public Instagram profile info.

    Returns dict:
        success          bool
        username         str
        full_name        str
        bio              str
        followers        int | None
        following        int | None
        posts_count      int | None
        profile_pic_url  str | None
        is_private       bool | None
        error            str
    """
    username = clean_username(username)
    result: dict = {
        "success":         False,
        "username":        username,
        "full_name":       username,
        "bio":             "",
        "followers":       None,
        "following":       None,
        "posts_count":     None,
        "profile_pic_url": None,
        "is_private":      None,
        "error":           "",
    }

    # ── Attempt 1: official internal API ─────────────────────────────
    api_url = (
        f"https://i.instagram.com/api/v1/users/web_profile_info/"
        f"?username={username}"
    )
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(
                api_url,
                headers={**_API_HEADERS,
                         "Referer": f"https://www.instagram.com/{username}/"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    ud = data.get("data", {}).get("user")
                    if ud:
                        result["success"]         = True
                        result["full_name"]        = ud.get("full_name") or username
                        result["bio"]              = ud.get("biography") or ""
                        result["is_private"]       = bool(ud.get("is_private", False))
                        result["profile_pic_url"]  = (
                            ud.get("profile_pic_url_hd") or ud.get("profile_pic_url")
                        )
                        result["followers"]        = (
                            ud.get("edge_followed_by", {}).get("count")
                        )
                        result["following"]        = (
                            ud.get("edge_follow", {}).get("count")
                        )
                        result["posts_count"]      = (
                            ud.get("edge_owner_to_timeline_media", {}).get("count")
                        )
                        return result
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as ex:
        logger.debug(f"fetch_profile attempt1: {ex}")

    # ── Attempt 2: scrape the page ────────────────────────────────────
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(
                f"https://www.instagram.com/{username}/",
                headers=_HEADERS,
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Try to extract JSON from page
                    m = re.search(
                        r'"user":\s*(\{"id":.+?"is_private":.+?})', text
                    )
                    if m:
                        try:
                            ud = json.loads(m.group(1))
                            result["success"]  = True
                            result["full_name"] = ud.get("full_name", username)
                            result["is_private"] = ud.get("is_private")
                            return result
                        except Exception:
                            pass
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as ex:
        logger.debug(f"fetch_profile attempt2: {ex}")

    if not result["error"]:
        result["error"] = "Could not fetch profile info."
    return result


# ─── Post / Reel fetcher ─────────────────────────────────────────────────────

async def fetch_post_info(url: str) -> dict:
    """
    Fetch public Instagram post / reel info.

    Returns dict:
        success          bool
        shortcode        str
        username         str
        full_name        str
        profile_pic_url  str | None
        thumbnail_url    str | None
        video_url        str | None
        caption          str
        like_count       int | None
        comment_count    int | None
        view_count       int | None
        is_video         bool
        is_private       bool
        error            str
    """
    shortcode = extract_shortcode(url) or url
    result: dict = {
        "success":         False,
        "shortcode":       shortcode,
        "username":        "",
        "full_name":       "",
        "profile_pic_url": None,
        "thumbnail_url":   None,
        "video_url":       None,
        "caption":         "",
        "like_count":      None,
        "comment_count":   None,
        "view_count":      None,
        "is_video":        False,
        "is_private":      False,
        "error":           "",
    }

    # ── Attempt 1: GraphQL endpoint ───────────────────────────────────
    gql_url = (
        f"https://www.instagram.com/api/v1/media/{shortcode}/info/"
        if shortcode and len(shortcode) < 20
        else None
    )
    # Use the public oEmbed endpoint first — it's the most reliable
    oembed_url = (
        f"https://www.instagram.com/oembed/?url=https://www.instagram.com/p/{shortcode}/"
    )
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(oembed_url, headers=_HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    result["success"]  = True
                    result["username"] = (
                        data.get("author_name") or data.get("author_url", "").split("/")[-2] or ""
                    )
                    result["thumbnail_url"] = data.get("thumbnail_url")
                    result["caption"] = data.get("title") or ""
                    return result
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as ex:
        logger.debug(f"fetch_post oembed: {ex}")

    # ── Attempt 2: Scrape post page for JSON ──────────────────────────
    post_url = f"https://www.instagram.com/p/{shortcode}/"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(post_url, headers=_HEADERS) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Try to find edge_media_to_parent_comment or similar
                    m = re.search(r'"shortcode_media":\s*(\{.+?\})\s*,\s*"edge_web_feed_timeline"', html, re.S)
                    if not m:
                        # Try JSON-LD
                        m2 = re.search(r'<script type="application/ld\+json"[^>]*>(.+?)</script>', html, re.S)
                        if m2:
                            try:
                                ld = json.loads(m2.group(1))
                                result["success"] = True
                                result["username"] = (ld.get("author", {}) or {}).get("alternateName", "")
                                result["thumbnail_url"] = (
                                    (ld.get("image", [None]) or [None])[0]
                                )
                                result["caption"] = ld.get("caption") or ld.get("description") or ""
                                return result
                            except Exception:
                                pass
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as ex:
        logger.debug(f"fetch_post scrape: {ex}")

    if not result["error"]:
        result["error"] = "Could not fetch post info — Instagram may be blocking requests."
    return result


# ─── Video downloader helper ─────────────────────────────────────────────────

async def fetch_reel_download_url(url: str) -> Optional[str]:
    """
    Try to obtain a direct video/thumbnail URL for a reel.
    Returns URL string or None.
    This is best-effort — Instagram blocks most scrapers.
    """
    shortcode = extract_shortcode(url)
    if not shortcode:
        return None
    # Thumbnail from oEmbed is the best we can reliably get
    oembed_url = (
        f"https://www.instagram.com/oembed/"
        f"?url=https://www.instagram.com/reel/{shortcode}/"
    )
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(oembed_url, headers=_HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data.get("thumbnail_url")
    except Exception:
        pass
    return None
