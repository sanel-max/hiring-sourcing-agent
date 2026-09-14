import os

import requests

SLACK_API = "https://slack.com/api"


def _token():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    return token


def _post(method, payload):
    resp = requests.post(
        f"{SLACK_API}/{method}",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        print(f"SLACK_ERROR: {method} -> {data}", flush=True)
    return data


def open_view(trigger_id, view):
    return _post("views.open", {"trigger_id": trigger_id, "view": view})


def post_message(channel, text, blocks=None, thread_ts=None):
    payload = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return _post("chat.postMessage", payload)


def update_message(channel, ts, text, blocks=None):
    payload = {"channel": channel, "ts": ts, "text": text}
    if blocks:
        payload["blocks"] = blocks
    return _post("chat.update", payload)
