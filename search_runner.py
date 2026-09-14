"""Runs one end-to-end search for a role: source candidates from every
configured platform, score each against the role's criteria, and post a
ranked summary back to Slack. Used both by the server's background task
(triggered from a Slack modal submission) and standalone for local testing.
"""

import os

from roles_store import load_role
from scoring import score_batch
from sourcing import search_all

MIN_FIT_SCORE_TO_SHOW = 50
TOP_N = 15


def _format_results_blocks(role, candidates, total_cost, errors, requested_by):
    ranked = sorted(candidates, key=lambda c: c.extra.get("fit_score", 0), reverse=True)
    shown = [c for c in ranked if c.extra.get("fit_score", 0) >= MIN_FIT_SCORE_TO_SHOW][:TOP_N]

    lines = [f"*Sourcing results for {role.name}* (requested by <@{requested_by}>)"]
    lines.append(f"Searched {', '.join(role.platforms)} -- {len(candidates)} candidates found, {len(shown)} shown (fit score >= {MIN_FIT_SCORE_TO_SHOW}).")
    if errors:
        lines.append(f"_Some platforms had errors: {'; '.join(errors)}_")
    lines.append(f"_Apify cost: ${total_cost:.2f}_")
    text = "\n".join(lines)

    if not shown:
        text += "\n\nNo candidates cleared the fit-score bar this run."
        return text

    for c in shown:
        score = c.extra.get("fit_score", 0)
        rationale = c.extra.get("rationale", "")
        text += f"\n\n*<{c.profile_url}|{c.name or c.handle}>* -- {c.platform}, fit {score}/100\n{rationale}"
    return text


def run_search(role_id, requested_by, channel):
    role = load_role(role_id)
    if role is None:
        raise ValueError(f"unknown role_id: {role_id}")

    candidates, total_cost, errors = search_all(role)
    scored = score_batch(candidates, role)

    from server.slack_client import post_message
    results_channel = os.environ.get("SLACK_RESULTS_CHANNEL", channel)
    text = _format_results_blocks(role, scored, total_cost, errors, requested_by)
    post_message(results_channel, text)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: python search_runner.py <role_id>")
    role = load_role(sys.argv[1])
    if role is None:
        sys.exit(f"unknown role_id: {sys.argv[1]}")
    candidates, total_cost, errors = search_all(role)
    scored = score_batch(candidates, role)
    print(_format_results_blocks(role, scored, total_cost, errors, "cli-test"))
