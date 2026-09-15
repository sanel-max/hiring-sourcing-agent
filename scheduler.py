"""Autonomous daily re-search for opted-in roles.

Runs inside the same always-on web service (see server/main.py's startup
background task) rather than as a separate Render Cron Job, so it can reuse
the exact same sourcing/scoring code path as a manual /source run. Every
~hour it checks which auto_search roles haven't run in the last
RUN_INTERVAL_HOURS and are still under DAILY_COST_CAP_USD for the day, and
runs them -- reporting only candidates not already seen for that role
(scored, not just filtered after the fact, so a repeat candidate costs
nothing), so this doesn't just re-surface the same people every day.
"""

import os
import time
import traceback

import scheduler_db
from export import build_candidates_workbook
from roles_store import list_roles, load_role
from scoring import score_batch
from sourcing import search_all

RUN_INTERVAL_HOURS = float(os.environ.get("SCHEDULER_RUN_INTERVAL_HOURS", "24"))
CHECK_EVERY_SECONDS = int(os.environ.get("SCHEDULER_CHECK_INTERVAL_SECONDS", "3600"))
DAILY_COST_CAP_USD = float(os.environ.get("DAILY_COST_CAP_USD", "10"))


def _due(role_id):
    last = scheduler_db.last_run_at(role_id)
    if last is None:
        return True
    return (time.time() - last) >= RUN_INTERVAL_HOURS * 3600


def _format_auto_results(role, new_candidates, total_cost, errors):
    ranked = sorted(new_candidates, key=lambda c: c.extra.get("fit_score", 0), reverse=True)
    lines = [f"\U0001f916 *Daily automated search for {role.name}*"]
    if not ranked:
        lines.append("No new candidates since the last run.")
        return "\n".join(lines)
    lines.append(f"{len(ranked)} new candidate(s) since the last run (not seen in any previous search for this role). Full list attached as a spreadsheet.")
    if errors:
        lines.append(f"_Some platforms had errors: {'; '.join(errors)}_")
    lines.append(f"_Apify cost: ${total_cost:.2f}_")
    text = "\n".join(lines)
    for c in ranked[:15]:
        score = c.extra.get("fit_score", 0)
        rationale = c.extra.get("rationale", "")
        text += f"\n\n*<{c.profile_url}|{c.name or c.handle}>* -- {c.platform}, fit {score}/100\n{rationale}"
    if len(ranked) > 15:
        text += f"\n\n_+{len(ranked) - 15} more in the attached spreadsheet._"
    return text


def run_role(role):
    from server.slack_client import post_message, upload_file

    results_channel = os.environ.get("SLACK_RESULTS_CHANNEL", "sourcing-search")

    candidates, total_cost, errors = search_all(role)
    new_candidates = scheduler_db.filter_unseen(role.id, candidates)
    scored = score_batch(new_candidates, role)

    text = _format_auto_results(role, scored, total_cost, errors)
    resp = post_message(results_channel, text)

    if scored and resp.get("channel"):
        try:
            xlsx_bytes = build_candidates_workbook(role, scored)
            safe_name = role.name.replace(" ", "_").replace("/", "-")
            upload_file(
                resp["channel"],
                filename=f"{safe_name}_new_candidates.xlsx",
                file_bytes=xlsx_bytes,
                title=f"{role.name} -- {len(scored)} new candidates",
                initial_comment=f"New candidates for *{role.name}* since the last automated search.",
            )
        except Exception as e:
            print(f"SCHEDULER_EXPORT_UPLOAD_FAILED: {e}", flush=True)

    scheduler_db.mark_seen(role.id, candidates)  # all found, not just new -- so they're not "new" again tomorrow
    scheduler_db.add_cost(total_cost)
    scheduler_db.record_run(role.id)
    print(f"SCHEDULER_RUN_DONE: role={role.id} found={len(candidates)} new={len(scored)} cost={total_cost:.2f}", flush=True)


def run_due_searches():
    spent_today = scheduler_db.today_cost()
    if spent_today >= DAILY_COST_CAP_USD:
        print(f"SCHEDULER_COST_CAP_HIT: spent=${spent_today:.2f} cap=${DAILY_COST_CAP_USD:.2f}, skipping this cycle", flush=True)
        return

    for summary in list_roles():
        role = load_role(summary["id"])
        if role is None or not role.auto_search or role.status == "archived":
            continue
        if not _due(role.id):
            continue
        if scheduler_db.today_cost() >= DAILY_COST_CAP_USD:
            print(f"SCHEDULER_COST_CAP_HIT: stopping mid-cycle, ${DAILY_COST_CAP_USD:.2f} cap reached", flush=True)
            break
        try:
            run_role(role)
        except Exception as e:
            print(f"SCHEDULER_ROLE_FAILED: role={role.id} error={e}", flush=True)
            traceback.print_exc()


def scheduler_loop():
    """Runs forever in a background thread (started from server/main.py).
    Sleeps first so a fresh deploy doesn't immediately fire every opted-in
    role before the service has even finished settling in."""
    time.sleep(60)
    while True:
        try:
            run_due_searches()
        except Exception as e:
            print(f"SCHEDULER_LOOP_ERROR: {e}", flush=True)
            traceback.print_exc()
        time.sleep(CHECK_EVERY_SECONDS)
