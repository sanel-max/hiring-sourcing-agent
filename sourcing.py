"""Candidate sourcing across LinkedIn, Twitter/X, and Instagram via Apify.

All three actors are public-data / no-login scrapers -- none of them log in
as a real LinkedIn/Twitter/Instagram account, so there's no risk of any
personal account getting flagged or restricted. If you swap in a different
actor later, keep that property unless you've deliberately decided the
richer (logged-in) data is worth the risk.

Actor input fields below are current as of when this was written -- Apify
actor schemas do change over time, so if a search starts returning nothing,
check the actor's own "API" tab on apify.com for its current input shape.
"""

import os

from apify_client import run_and_fetch
from models import Candidate

LINKEDIN_ACTOR = "harvestapi~linkedin-profile-search"
TWITTER_ACTOR = "data_direct~twitter-users-scraper"
INSTAGRAM_ACTOR = "khadinakbar~instagram-user-search-scraper"


def _token():
    token = os.environ.get("APIFY_API_KEY")
    if not token:
        raise RuntimeError("APIFY_API_KEY not set")
    return token


def search_linkedin(role, max_items=40):
    query = " ".join(role.keywords) or role.name
    run_input = {
        "searchQuery": query,
        "currentJobTitles": role.keywords or [role.name],
        "profileScraperMode": "Short",
        "maxItems": max_items,
    }
    if role.location:
        run_input["locations"] = [role.location]
    items, cost = run_and_fetch(_token(), LINKEDIN_ACTOR, run_input, "linkedin-search", timeout_secs=900)
    candidates = []
    for item in items:
        handle = item.get("publicIdentifier") or item.get("username") or ""
        candidates.append(Candidate(
            platform="linkedin",
            handle=handle,
            name=item.get("name") or item.get("fullName") or "",
            profile_url=item.get("profileUrl") or item.get("url") or (f"https://linkedin.com/in/{handle}" if handle else ""),
            bio=item.get("about") or "",
            headline=item.get("headline") or "",
            extra=item,
        ))
    return candidates, cost


def search_twitter(role, pages=1):
    query = " ".join(role.keywords) or role.name
    items, cost = run_and_fetch(_token(), TWITTER_ACTOR, {"query": query, "pages": pages}, "twitter-search", timeout_secs=300)
    candidates = []
    for item in items:
        handle = item.get("username") or item.get("screen_name") or ""
        candidates.append(Candidate(
            platform="twitter",
            handle=handle,
            name=item.get("name") or item.get("displayName") or "",
            profile_url=item.get("url") or (f"https://x.com/{handle}" if handle else ""),
            bio=item.get("description") or item.get("bio") or "",
            extra=item,
        ))
    return candidates, cost


def search_instagram(role, max_results=50):
    query = " ".join(role.keywords) or role.name
    run_input = {
        "searchQueries": [query],
        "maxResultsPerQuery": min(max_results, 50),
        "maxResults": max_results,
    }
    items, cost = run_and_fetch(_token(), INSTAGRAM_ACTOR, run_input, "instagram-search", timeout_secs=600)
    candidates = []
    for item in items:
        handle = item.get("username") or ""
        candidates.append(Candidate(
            platform="instagram",
            handle=handle,
            name=item.get("fullName") or "",
            profile_url=item.get("url") or (f"https://instagram.com/{handle}" if handle else ""),
            bio=item.get("biography") or item.get("bio") or "",
            extra=item,
        ))
    return candidates, cost


PLATFORM_SEARCHERS = {
    "linkedin": search_linkedin,
    "twitter": search_twitter,
    "instagram": search_instagram,
}


def clean_candidates(candidates):
    """Structural cleanup only -- no judgment calls about fit, just removing
    junk the search actors sometimes return: duplicates (the same handle can
    turn up more than once within a platform's results) and profiles with
    nothing on them to even look at (no handle, or no name/bio/headline at
    all). Everything else -- whether a candidate is actually a good fit --
    is left to scoring (as a sort hint) and ultimately the hiring team."""
    seen = set()
    cleaned = []
    for c in candidates:
        if not c.handle:
            continue
        key = (c.platform, c.handle.lower())
        if key in seen:
            continue
        seen.add(key)
        if not (c.name or c.bio or c.headline):
            continue
        cleaned.append(c)
    return cleaned


def search_all(role):
    """Runs every platform listed in role.platforms.
    Returns (candidates, total_cost, errors) -- errors is a list of
    "<platform>: <message>" strings for platforms that failed, so one
    broken actor doesn't take down the whole search."""
    all_candidates = []
    total_cost = 0.0
    errors = []
    for platform in role.platforms:
        searcher = PLATFORM_SEARCHERS.get(platform)
        if not searcher:
            continue
        try:
            candidates, cost = searcher(role)
            all_candidates.extend(candidates)
            total_cost += cost
        except Exception as e:
            errors.append(f"{platform}: {e}")
    return clean_candidates(all_candidates), total_cost, errors
