"""Loads role criteria from the roles/ directory.

roles/index.json is a flat list of {"id": ..., "name": ...} used to
populate the Slack modal's dropdown. roles/<id>.json holds the full
criteria for that role (Role.from_dict shape).

These files are a synced snapshot of the Roles dashboard artifact -- ask
Claude Code to "sync roles" after adding/editing one there, which reads the
dashboard's database and rewrites these files, then commits + pushes so
Render redeploys with the update. This mirrors the sibling UGC project's
campaign-sync flow.
"""

import json
import os

from models import Role

ROLES_DIR = os.path.join(os.path.dirname(__file__), "roles")
INDEX_PATH = os.path.join(ROLES_DIR, "index.json")


def list_roles():
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH) as f:
        return json.load(f)


def load_role(role_id):
    path = os.path.join(ROLES_DIR, f"{role_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return Role.from_dict(json.load(f))
