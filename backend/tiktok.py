"""Look up a TikTok shop and sample what buyers say under its videos.

Two Apify actors do the fetching, run with the account behind APIFY_TOKEN:

- clockworks/tiktok-profile-scraper: the profile (bio, followers, seller flag)
  and the latest videos.
- clockworks/tiktok-comments-scraper: a few comments per video.

Cost is per result on Apify (about $0.003 per profile or video, $0.00125 per
comment), so every call is capped. A default lookup is 3 videos and 15
comments, about $0.02, which the Apify free plan's monthly credit covers many
times over.

The comments go through the same on-box classifier as buyer reports. A lookup
only reads and classifies. Nothing is saved or scored unless the caller asks.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from classifier import classify_report

PROFILE_ACTOR = "clockworks~tiktok-profile-scraper"
COMMENTS_ACTOR = "clockworks~tiktok-comments-scraper"

MAX_VIDEOS = 5
MAX_COMMENTS_PER_VIDEO = 10
RUN_TIMEOUT_SECONDS = 240

HANDLE_RE = re.compile(r"^[A-Za-z0-9_.]{2,24}$")
URL_HANDLE_RE = re.compile(r"tiktok\.com/@([A-Za-z0-9_.]{2,24})", re.IGNORECASE)


class TikTokError(RuntimeError):
    """A lookup that cannot continue. The message is safe to show the user."""


def parse_handle(value: str) -> str | None:
    """A TikTok handle from a profile link, a video link, @handle, or a bare handle.

    A name with spaces is not a handle, so it returns None and the caller can
    look the shop up by name in VeriDuka instead. Short links (vm.tiktok.com)
    cannot be read without following a redirect, so they also return None.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    match = URL_HANDLE_RE.search(raw)
    if match:
        return match.group(1).lower().rstrip(".")
    candidate = raw.lstrip("@")
    if HANDLE_RE.fullmatch(candidate):
        return candidate.lower().rstrip(".")
    return None


def _token() -> str:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise TikTokError("TikTok lookup is not connected. Add APIFY_TOKEN to .env.")
    return token


def _api(method: str, path: str, token: str, body: dict | None = None) -> dict | list:
    request = urllib.request.Request(
        f"https://api.apify.com/v2/{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise TikTokError("Apify refused the token. Check APIFY_TOKEN.") from exc
        if exc.code == 402:
            raise TikTokError("The Apify account is out of credit for this month.") from exc
        raise TikTokError(f"Apify returned {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TikTokError("Could not reach Apify.") from exc


def run_actor(actor: str, actor_input: dict, token: str | None = None) -> list[dict]:
    """Start an actor, wait for it, and return its dataset items."""
    token = token or _token()
    started = _api("POST", f"acts/{actor}/runs", token, actor_input)
    run = started.get("data", {}) if isinstance(started, dict) else {}
    run_id = run.get("id")
    if not run_id:
        raise TikTokError("Apify did not start the run.")

    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while run.get("status") in {"READY", "RUNNING", "TIMING-OUT", None}:
        if time.monotonic() > deadline:
            _api("POST", f"actor-runs/{run_id}/abort", token)
            raise TikTokError("TikTok took too long to answer. Try again in a minute.")
        time.sleep(3)
        polled = _api("GET", f"actor-runs/{run_id}", token)
        run = polled.get("data", {}) if isinstance(polled, dict) else {}
    if run.get("status") != "SUCCEEDED":
        raise TikTokError(f"The TikTok fetch ended as {run.get('status', 'unknown')}.")

    dataset = run.get("defaultDatasetId")
    items = _api("GET", f"datasets/{dataset}/items?clean=true&format=json", token)
    return items if isinstance(items, list) else []


def fetch_profile(handle: str, videos: int, token: str | None = None) -> tuple[dict, list[dict]]:
    """(profile, videos) for a handle. Raises TikTokError when the account is not found."""
    items = run_actor(
        PROFILE_ACTOR,
        {
            "profiles": [handle],
            "resultsPerPage": videos,
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "excludePinnedPosts": True,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSlideshowImages": False,
        },
        token,
    )
    posts = [item for item in items if isinstance(item.get("authorMeta"), dict) and item["authorMeta"].get("name")]
    if not posts:
        raise TikTokError(f"No public TikTok account found for @{handle}.")
    return shape_profile(posts[0]["authorMeta"]), [shape_video(item) for item in posts]


def fetch_comments(video_urls: list[str], per_video: int, token: str | None = None) -> list[dict]:
    if not video_urls:
        return []
    return run_actor(
        COMMENTS_ACTOR,
        {"postURLs": video_urls, "commentsPerPost": per_video, "maxRepliesPerComment": 0},
        token,
    )


def shape_profile(meta: dict) -> dict:
    commerce = meta.get("commerceUserInfo") or {}
    return {
        "handle": str(meta.get("name") or "").lower(),
        "nickname": meta.get("nickName") or meta.get("name") or "",
        "profile_url": meta.get("profileUrl") or f"https://www.tiktok.com/@{meta.get('name')}",
        "verified": bool(meta.get("verified")),
        "bio": (meta.get("signature") or "").strip(),
        "bio_link": meta.get("bioLink") or None,
        "followers": int(meta.get("fans") or 0),
        "likes": int(meta.get("heart") or 0),
        "videos": int(meta.get("video") or 0),
        "private": bool(meta.get("privateAccount")),
        "tiktok_seller": bool(meta.get("ttSeller")),
        "business_account": bool(commerce.get("commerceUser")),
        "business_category": commerce.get("category") or None,
    }


def shape_video(item: dict) -> dict:
    return {
        "url": item.get("webVideoUrl") or "",
        "text": (item.get("text") or "").strip(),
        "comment_count": int(item.get("commentCount") or 0),
        "plays": int(item.get("playCount") or 0),
        "has_shop_product": bool(item.get("hasTikTokShopProduct")),
    }


def classify_comments(raw_comments: list[dict]) -> list[dict]:
    """Run each comment through the on-box classifier. Empty and emoji-only comments are skipped."""
    out = []
    seen: set[str] = set()
    for item in raw_comments:
        text = " ".join(str(item.get("text") or "").split())
        cid = str(item.get("cid") or "")
        if len(text) < 3 or (cid and cid in seen):
            continue
        if cid:
            seen.add(cid)
        result = classify_report(text, None)
        out.append(
            {
                "external_id": f"tt:{cid}" if cid else None,
                "text": text,
                "author": item.get("uniqueId") or "",
                "video_url": item.get("videoWebUrl") or item.get("submittedVideoUrl") or "",
                "likes": int(item.get("diggCount") or 0),
                "classification": result.as_dict(),
            }
        )
    return out


def summarize(comments: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for comment in comments:
        category = comment["classification"]["category"]
        counts[category] = counts.get(category, 0) + 1
    return counts


def lookup(handle: str, videos: int = 3, comments_per_video: int = 5) -> dict:
    """Profile, sampled comments, and a classification of each comment."""
    videos = max(1, min(videos, MAX_VIDEOS))
    comments_per_video = max(1, min(comments_per_video, MAX_COMMENTS_PER_VIDEO))
    token = _token()
    profile, posts = fetch_profile(handle, videos, token)
    commented = [post["url"] for post in posts if post["url"] and post["comment_count"] > 0]
    comments = classify_comments(fetch_comments(commented, comments_per_video, token))
    return {"profile": profile, "videos": posts, "comments": comments, "summary": summarize(comments)}
