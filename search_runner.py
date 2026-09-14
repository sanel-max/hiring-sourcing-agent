"""Runs one end-to-end search for a role: source candidates from every
configured platform, score each against the role's criteria, and post the
results back to Slack. Used both by the server's background task
(triggered from a Slack modal submission) and standalone for local testing.

Design intent: this is a broad-net starting point, not a hiring decision.
Every candidate that clears the structural cleanup in sourcing.clean_candidates
gets shown -- sorted by Claude's fit score, which is a sort hint, not a pass/
fail gate. That matters most for creative roles where "good fit" can't be
written down as a concrete example (see the SFX role) -- the model has less
to go on, so silently dropping anyone under a score threshold would be the
tool making a judgment call that belongs to the hiring team. Binary filter
results are shown per-candidate (pass/fail/unclear) so the team can scan and
filter themselves rather than the tool doing it for them.
"""

import os

from roles_store import load_role
from scoring import score_batch
from sourcing import search_all

# Purely a Slack-message-length safety valve, not a quality bar -- if a
# search finds more than this, everyone still gets scored, just not all
# printed into one message.
MAX_RESULTS_PER_MESSAGE = 40

FILTER_ICONS = {True: "✅", False: "❌", None: "❔"}  # ✅ ❌ ❔


def _binary_filter_line(candidate):
    results = candidate.extra.get("binary_filter_results") or []
    if not results:
        return ""
    parts = [f"{FILTER_ICONS.get(r.get('passes'), '❔')} {r.get('label', '')}" for r in results]
    return "  ".join(parts)


def _format_results_blocks(role, candidates, total_cost, errors, requested_by):
    ranked = sorted(candidates, key=lambda c: c.extra.get("fit_score", 0), reverse=True)
    shown = ranked[:MAX_RESULTS_PER_MESSAGE]
    truncated = len(ranked) - len(shown)

    lines = [f"*Sourcing results for {role.name}* (requested by <@{requested_by}>)"]
    lines.append(f"Searched {', '.join(role.platforms)} -- {len(candidates)} candidates found, sorted by fit score below. Fit score is a starting-point sort, not a filter -- review below that line too if the top ones aren't right.")
    if truncated > 0:
        lines.append(f"_Showing top {len(shown)} of {len(candidates)} -- {truncated} more not shown here, narrow the keywords to see them._")
    if errors:
        lines.append(f"_Some platforms had errors: {'; '.join(errors)}_")
    lines.append(f"_Apify cost: ${total_cost:.2f}_")
    text = "\n".join(lines)

    if not shown:
        text += "\n\nNo candidates found this run -- try broadening the keywords."
        return text

    for c in shown:
        score = c.extra.get("fit_score", 0)
        rationale = c.extra.get("rationale", "")
        entry = f"\n\n*<{c.profile_url}|{c.name or c.handle}>* -- {c.platform}, fit {score}/100\n{rationale}"
        filter_line = _binary_filter_line(c)
        if filter_line:
            entry += f"\n{filter_line}"
        text += entry
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
