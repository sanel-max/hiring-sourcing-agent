"""Thin Apify REST wrapper -- same run/poll/fetch pattern used by the sibling
UGC creator project's competitor_scraper.py, so behavior (auth, error
logging, cost tracking) stays consistent across both."""

import json
import time

import requests

API = "https://api.apify.com/v2"


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _check(resp):
    if not resp.ok:
        print("APIFY_ERROR: " + json.dumps({"status": resp.status_code, "url": resp.url.split("?")[0], "body": resp.text[:1000]}), flush=True)
    resp.raise_for_status()


def start_run(token, actor_id, run_input, memory_mb=1024, timeout_secs=600):
    resp = requests.post(
        f"{API}/acts/{actor_id}/runs",
        params={"memory": memory_mb, "timeout": timeout_secs},
        headers=_auth_headers(token),
        json=run_input,
        timeout=60,
    )
    _check(resp)
    data = resp.json()["data"]
    print(f"Started run {data['id']} for actor {actor_id} (status={data['status']})")
    return data["id"]


def poll_run(token, run_id, label, poll_every=8, max_wait=600):
    waited = 0
    while waited < max_wait:
        resp = requests.get(f"{API}/actor-runs/{run_id}", headers=_auth_headers(token), timeout=60)
        _check(resp)
        data = resp.json()["data"]
        status = data["status"]
        print(f"[{label}] run {run_id} status={status} (waited {waited}s)")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return data
        time.sleep(poll_every)
        waited += poll_every
    raise TimeoutError(f"[{label}] run {run_id} did not finish within {max_wait}s")


def fetch_dataset_items(token, dataset_id):
    items = []
    offset = 0
    limit = 1000
    while True:
        resp = requests.get(
            f"{API}/datasets/{dataset_id}/items",
            params={"format": "json", "clean": "true", "offset": offset, "limit": limit},
            headers=_auth_headers(token),
            timeout=120,
        )
        _check(resp)
        batch = resp.json()
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items


def run_and_fetch(token, actor_id, run_input, label, memory_mb=1024, timeout_secs=600):
    run_id = start_run(token, actor_id, run_input, memory_mb, timeout_secs)
    final = poll_run(token, run_id, label, max_wait=timeout_secs)
    cost = final.get("usageTotalUsd") or 0.0
    print(f"[{label}] finished status={final['status']} cost=${cost:.4f}")
    if final["status"] != "SUCCEEDED":
        print(f"[{label}] WARNING: run did not succeed, using whatever dataset items exist anyway")
    items = fetch_dataset_items(token, final["defaultDatasetId"])
    print(f"[{label}] fetched {len(items)} dataset items")
    return items, cost
