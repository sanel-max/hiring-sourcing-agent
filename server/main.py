import json
import os
import sys
import traceback
from urllib.parse import parse_qsl

from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roles_store import list_roles
from search_runner import run_search
from server.slack_client import open_view, post_message
from server.slack_verify import SignatureError, verify

app = FastAPI()

ROLE_SELECT_BLOCK_ID = "role_block"
ROLE_SELECT_ACTION_ID = "role_select"


def _role_modal_view():
    roles = list_roles()
    if not roles:
        return {
            "type": "modal",
            "callback_id": "search_submit",
            "title": {"type": "plain_text", "text": "Source candidates"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "No roles have been set up yet -- add one on the Roles dashboard first."},
            }],
        }

    options = [
        {"text": {"type": "plain_text", "text": r["name"]}, "value": r["id"]}
        for r in roles
    ]
    return {
        "type": "modal",
        "callback_id": "search_submit",
        "title": {"type": "plain_text", "text": "Source candidates"},
        "submit": {"type": "plain_text", "text": "Search"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [{
            "type": "input",
            "block_id": ROLE_SELECT_BLOCK_ID,
            "label": {"type": "plain_text", "text": "Which role?"},
            "element": {
                "type": "static_select",
                "action_id": ROLE_SELECT_ACTION_ID,
                "options": options,
                "placeholder": {"type": "plain_text", "text": "Select a role"},
            },
        }],
    }


async def _verify_request(request: Request):
    raw_body = await request.body()
    verify(
        raw_body,
        request.headers.get("x-slack-request-timestamp"),
        request.headers.get("x-slack-signature"),
    )
    return raw_body


def _run_search_background(role_id, requested_by, channel):
    try:
        run_search(role_id, requested_by, channel)
    except Exception as e:
        print("SEARCH_ERROR: " + json.dumps({"role_id": role_id, "error": str(e)}), flush=True)
        traceback.print_exc()
        try:
            post_message(channel, f"Sourcing search for role `{role_id}` failed: {e}")
        except Exception:
            pass


@app.post("/slack/commands")
async def slack_commands(request: Request):
    try:
        raw_body = await _verify_request(request)
    except SignatureError as e:
        print(f"SLACK_AUTH_ERROR on /slack/commands: {e}", flush=True)
        return PlainTextResponse(str(e), status_code=401)

    form = dict(parse_qsl(raw_body.decode("utf-8")))
    trigger_id = form.get("trigger_id")
    open_view(trigger_id, _role_modal_view())
    return PlainTextResponse("")  # empty 200: modal is the only visible response


@app.post("/slack/interactions")
async def slack_interactions(request: Request, background_tasks: BackgroundTasks):
    try:
        raw_body = await _verify_request(request)
    except SignatureError as e:
        print(f"SLACK_AUTH_ERROR on /slack/interactions: {e}", flush=True)
        return PlainTextResponse(str(e), status_code=401)

    form = dict(parse_qsl(raw_body.decode("utf-8")))
    payload = json.loads(form["payload"])

    if payload.get("type") != "view_submission" or payload.get("view", {}).get("callback_id") != "search_submit":
        return PlainTextResponse("")

    values = payload["view"]["state"]["values"]
    role_id = values[ROLE_SELECT_BLOCK_ID][ROLE_SELECT_ACTION_ID]["selected_option"]["value"]
    requested_by = payload["user"]["id"]
    channel = os.environ.get("SLACK_RESULTS_CHANNEL", "sourcing-search")

    background_tasks.add_task(_run_search_background, role_id, requested_by, channel)

    # ack immediately (closes the modal); results land in the channel once the search finishes
    return JSONResponse({"response_action": "clear"})


@app.get("/healthz")
async def healthz():
    return {"ok": True}
