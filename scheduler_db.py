"""Persistent state for the autonomous scheduler: which candidates have
already been surfaced per role (so a daily re-search only reports genuinely
new people, not the same ones every day), when each role last ran, and
cumulative daily spend (for the cost ceiling).

Lives on a Render persistent Disk (see render.yaml) at SCHEDULER_DB_PATH --
the default web service filesystem is wiped on every deploy, which would
silently reset all of this (re-reporting everyone as "new" the next time
code changes). Falls back to a local file for local testing.
"""

import os
import sqlite3
import time

DB_PATH = os.environ.get("SCHEDULER_DB_PATH", os.path.join(os.path.dirname(__file__), "scheduler.db"))


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS seen_candidates (
            role_id TEXT, platform TEXT, handle TEXT, first_seen_at TEXT,
            PRIMARY KEY (role_id, platform, handle)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS role_runs (
            role_id TEXT PRIMARY KEY, last_run_at REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS daily_cost (
            date TEXT PRIMARY KEY, total_cost REAL NOT NULL DEFAULT 0
        )"""
    )
    conn.commit()
    return conn


def filter_unseen(role_id, candidates):
    """Returns only the candidates not already recorded as seen for this
    role -- call BEFORE scoring, so already-seen candidates cost nothing
    (no repeat Anthropic calls), not just get hidden after the fact."""
    conn = _connect()
    try:
        seen = {
            row[0] for row in conn.execute(
                "SELECT platform || ':' || handle FROM seen_candidates WHERE role_id = ?", (role_id,)
            )
        }
        return [c for c in candidates if f"{c.platform}:{c.handle.lower()}" not in seen]
    finally:
        conn.close()


def mark_seen(role_id, candidates):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_candidates (role_id, platform, handle, first_seen_at) VALUES (?, ?, ?, ?)",
            [(role_id, c.platform, c.handle.lower(), now) for c in candidates],
        )
        conn.commit()
    finally:
        conn.close()


def last_run_at(role_id):
    conn = _connect()
    try:
        row = conn.execute("SELECT last_run_at FROM role_runs WHERE role_id = ?", (role_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def record_run(role_id):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO role_runs (role_id, last_run_at) VALUES (?, ?) "
            "ON CONFLICT(role_id) DO UPDATE SET last_run_at = excluded.last_run_at",
            (role_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def today_cost():
    today = time.strftime("%Y-%m-%d", time.gmtime())
    conn = _connect()
    try:
        row = conn.execute("SELECT total_cost FROM daily_cost WHERE date = ?", (today,)).fetchone()
        return row[0] if row else 0.0
    finally:
        conn.close()


def add_cost(amount):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO daily_cost (date, total_cost) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET total_cost = total_cost + excluded.total_cost",
            (today, amount),
        )
        conn.commit()
    finally:
        conn.close()
