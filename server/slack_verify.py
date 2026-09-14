"""Verifies the Slack request signature so nobody but Slack can hit our
endpoints and trigger a paid Apify search. See:
https://api.slack.com/authentication/verifying-requests-from-slack
"""

import hashlib
import hmac
import os
import time


class SignatureError(Exception):
    pass


def verify(raw_body: bytes, timestamp: str, signature: str):
    secret = os.environ.get("SLACK_SIGNING_SECRET")
    if not secret:
        raise SignatureError("SLACK_SIGNING_SECRET not set")
    if not timestamp or not signature:
        raise SignatureError("missing Slack signature headers")

    # Reject anything older than 5 minutes -- prevents replaying a captured request.
    if abs(time.time() - float(timestamp)) > 60 * 5:
        raise SignatureError("stale request timestamp")

    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise SignatureError("signature mismatch")
