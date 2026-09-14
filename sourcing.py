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


TARGET_RESULTS_PER_PLATFORM = 100


def search_linkedin(role, target_total=TARGET_RESULTS_PER_PLATFORM):
    # This actor takes one searchQuery string per call, not a list -- joining
    # all keywords into one string would search for that exact combined
    # phrase (near-zero matches) instead of "any of these." So one actor run
    # per keyword instead, aggregated, each capped to keep the total near
    # target_total rather than target_total-per-keyword.
    keywords = role.keywords or [role.name]
    per_keyword_max = max(15, target_total // len(keywords))
    candidates = []
    total_cost = 0.0
    for kw in keywords:
        run_input = {
            "searchQuery": kw,
            "currentJobTitles": [kw],
            "profileScraperMode": "Short",
            "maxItems": per_keyword_max,
        }
        if role.location:
            run_input["locations"] = [role.location]
        items, cost = run_and_fetch(_token(), LINKEDIN_ACTOR, run_input, f"linkedin-search:{kw}", timeout_secs=900)
        total_cost += cost
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
    return candidates, total_cost


def search_twitter(role, target_total=TARGET_RESULTS_PER_PLATFORM, pages_per_keyword=2):
    # Same one-query-per-call constraint as LinkedIn -- search each keyword
    # separately rather than one combined (and effectively unmatchable) string.
    keywords = role.keywords or [role.name]
    candidates = []
    total_cost = 0.0
    for kw in keywords:
        items, cost = run_and_fetch(_token(), TWITTER_ACTOR, {"query": kw, "pages": pages_per_keyword}, f"twitter-search:{kw}", timeout_secs=300)
        total_cost += cost
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
    return candidates, total_cost


def search_instagram(role, target_total=TARGET_RESULTS_PER_PLATFORM):
    # This actor's searchQueries field natively takes a list -- one call
    # searches every keyword, no need to loop like the other two platforms.
    keywords = role.keywords or [role.name]
    per_keyword_max = max(20, target_total // len(keywords))
    run_input = {
        "searchQueries": keywords,
        "maxResultsPerQuery": per_keyword_max,
        "maxResults": target_total,
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


PLATFORM_LABELS = {
    "linkedin": "Searching LinkedIn",
    "twitter": "Searching X/Twitter",
    "instagram": "Searching Instagram",
}


def search_all(role, progress=None):
    """Runs every platform listed in role.platforms.
    Returns (candidates, total_cost, errors) -- errors is a list of
    "<platform>: <message>" strings for platforms that failed, so one
    broken actor doesn't take down the whole search.

    progress: optional SlackProgress (see progress.py) -- if given, calls
    .step(label) before each platform and .advance() after, so the Slack
    status message updates as the search moves through platforms."""
    all_candidates = []
    total_cost = 0.0
    errors = []
    for platform in role.platforms:
        searcher = PLATFORM_SEARCHERS.get(platform)
        if not searcher:
            continue
        if progress:
            progress.step(PLATFORM_LABELS.get(platform, f"Searching {platform}"))
        try:
            candidates, cost = searcher(role)
            all_candidates.extend(candidates)
            total_cost += cost
        except Exception as e:
            errors.append(f"{platform}: {e}")
        if progress:
            progress.advance()
    return clean_candidates(all_candidates), total_cost, errors
