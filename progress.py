"""Live-updating Slack status message for a running search: one message
posted at the start, then edited in place (chat.update) as the search moves
through stages -- so the channel shows "Searching LinkedIn... ~2 min left"
instead of going quiet for however long the run takes.

Same idea as ProgressTracker in the sibling creator project's
competitor_scraper.py: track elapsed time per completed step, estimate what's
left from the average pace so far. Rough by nature -- it's a "roughly how
much longer" indicator, not a precise ETA.
"""

import time

from server.slack_client import post_message, update_message


def _format_remaining(seconds):
    if seconds is None:
        return ""
    if seconds < 60:
        return f"~{max(5, round(seconds / 5) * 5)}s left"
    return f"~{max(1, round(seconds / 60))} min left"


class SlackProgress:
    def __init__(self, channel, role_name, total_steps):
        self.channel_name = channel
        self.role_name = role_name
        self.total_steps = max(total_steps, 1)
        self.completed_steps = 0
        self.started_at = time.time()
        self.channel_id = None
        self.ts = None
        self._phase_label = None
        self._phase_started_at = None
        try:
            resp = post_message(channel, f"\U0001f50d Starting search for *{role_name}*…")
            if resp.get("ok"):
                self.channel_id = resp["channel"]
                self.ts = resp["ts"]
        except Exception as e:
            print(f"PROGRESS_START_FAILED: {e}", flush=True)

    def step(self, label):
        """Call right before starting a new stage. label: a short 2-4 word
        description, e.g. 'Searching LinkedIn' or 'Scoring candidates'."""
        elapsed = time.time() - self.started_at
        remaining = None
        if self.completed_steps > 0:
            avg = elapsed / self.completed_steps
            remaining = avg * (self.total_steps - self.completed_steps)
        text = f"\U0001f50d {label}… ({self.completed_steps}/{self.total_steps} steps"
        eta = _format_remaining(remaining)
        text += f", {eta})" if eta else ")"
        self._update(text)

    def advance(self):
        """Call right after a stage finishes, before the next step()."""
        self.completed_steps += 1

    def note(self, text):
        """Ad-hoc update outside the fixed step count -- for a phase (like
        scoring) whose length isn't known until it's already running."""
        self._update(f"\U0001f50d {text}…")

    def note_progress(self, done, total, label):
        """Like note(), but with its own ETA -- tracked from this phase's own
        elapsed time (not the whole search's), since a phase like scoring N
        candidates has a very different per-unit pace than searching a
        platform. First call for a given label starts that phase's clock."""
        now = time.time()
        if self._phase_label != label:
            self._phase_started_at = now
            self._phase_label = label
        elapsed = now - self._phase_started_at
        remaining = None
        if done > 0 and total > done:
            avg = elapsed / done
            remaining = avg * (total - done)
        text = f"\U0001f50d {label} ({done}/{total}"
        eta = _format_remaining(remaining)
        text += f", {eta})" if eta else ")"
        self._update(text)

    def finish(self, final_text):
        self._update(final_text)

    def _update(self, text):
        if not self.ts:
            return
        try:
            update_message(self.channel_id, self.ts, text)
        except Exception as e:
            print(f"PROGRESS_UPDATE_FAILED: {e}", flush=True)
