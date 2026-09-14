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


def upload_file(channel, filename, file_bytes, title=None, initial_comment=None, thread_ts=None):
    """Slack's current (non-deprecated) 3-step upload flow: get a scoped
    upload URL, PUT the bytes there, then tell Slack to attach the
    finished upload to a channel. channel should be a real channel ID
    (e.g. from a prior post_message response's "channel" field) -- unlike
    chat.postMessage, this step doesn't reliably resolve a bare channel
    name."""
    url_resp = requests.post(
        f"{SLACK_API}/files.getUploadURLExternal",
        headers={"Authorization": f"Bearer {_token()}"},
        data={"filename": filename, "length": len(file_bytes)},
        timeout=30,
    )
    url_resp.raise_for_status()
    url_data = url_resp.json()
    if not url_data.get("ok"):
        print(f"SLACK_ERROR: files.getUploadURLExternal -> {url_data}", flush=True)
        return url_data

    put_resp = requests.post(url_data["upload_url"], files={"file": (filename, file_bytes)}, timeout=60)
    put_resp.raise_for_status()

    complete_payload = {
        "files": [{"id": url_data["file_id"], "title": title or filename}],
        "channel_id": channel,
    }
    if initial_comment:
        complete_payload["initial_comment"] = initial_comment
    if thread_ts:
        complete_payload["thread_ts"] = thread_ts
    return _post("files.completeUploadExternal", complete_payload)
