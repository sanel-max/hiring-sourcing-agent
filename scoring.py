"""Scores a sourced candidate against a Role's criteria using Claude:
the job description, free-text good/bad examples, and the role's binary
filters (e.g. "worked as X for 12+ months") -- judged from whatever bio/
headline/profile text the sourcing actor returned, not from a full resume.
"""

import json
import os

from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM = """You are screening a sourced social/professional profile against a specific
open role. You only have what's in the profile's bio/headline/public fields -- not a
resume or an interview -- so judge on plausibility, not certainty.

Return ONLY valid JSON, no markdown fences, no preamble, in this exact shape:
{"fit_score": <0-100 integer>, "rationale": "<1-2 sentences a recruiter can skim>",
"binary_filter_results": [{"label": "<filter label, verbatim>", "passes": <true|false|null>,
"reason": "<short reason; null means the profile doesn't give enough info to judge>"}]}

Scoring guidance:
- fit_score reflects overall match to the job description, and to the good/bad examples
  when they're given -- good_examples/bad_examples are often blank (especially for creative
  roles where "good" can't be written down as text), and that's expected, not a problem to
  work around. Score off the job description alone in that case; don't invent your own
  notion of what a good example looks like to fill the gap.
- A binary filter is null (not false) when the profile simply doesn't mention it -- don't
  assume a red flag from silence.
- Weight a failed binary filter heavily in fit_score; weight a null one only lightly.
- This is a first-pass shortlist a human will review, not a hiring decision -- when genuinely
  unsure, score toward the middle rather than a harsh low score, and say so in the rationale.
  False negatives (a good candidate scored low and never looked at) are worse here than false
  positives (a mediocre one the human quickly rules out).
"""


def score_candidate(candidate, role):
    payload = {
        "role_name": role.name,
        "job_description": role.job_description,
        "good_examples": role.good_examples,
        "bad_examples": role.bad_examples,
        "binary_filters": [{"label": f.label, "description": f.description} for f in role.binary_filters],
        "candidate": {
            "platform": candidate.platform,
            "handle": candidate.handle,
            "name": candidate.name,
            "headline": candidate.headline,
            "bio": candidate.bio,
        },
    }

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )

    text = response.content[0].text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(text)
        candidate.extra["fit_score"] = result["fit_score"]
        candidate.extra["rationale"] = result["rationale"]
        candidate.extra["binary_filter_results"] = result.get("binary_filter_results", [])
    except (json.JSONDecodeError, KeyError) as e:
        candidate.extra["fit_score"] = 0
        candidate.extra["rationale"] = f"SCORING FAILED: {e} | raw: {text[:200]}"
        candidate.extra["binary_filter_results"] = []

    return candidate


def score_batch(candidates, role):
    return [score_candidate(c, role) for c in candidates]
