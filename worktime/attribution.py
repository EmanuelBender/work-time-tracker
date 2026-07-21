"""Resolve a detected activity to a billing project.

The chain: file match (a document under a registered project folder), then a
learned rule (app / url_domain / title_contains), else unassigned. Session
inference — carrying the last strong project context — lives in the tracker.
"""

import os
import urllib.parse


def _folder_match(file_path, folders):
    """project_id of the longest registered folder that is a prefix of file_path.
    `folders` is a list of {path, project_id} (a project may own several)."""
    if not file_path:
        return None
    best, best_len = None, -1
    for f in folders:
        path = (f.get("path") or "").rstrip("/")
        if not path:
            continue
        if file_path == path or file_path.startswith(path + "/"):
            if len(path) > best_len:
                best, best_len = f["project_id"], len(path)
    return best


def url_domain(url):
    """Lowercase hostname of a URL, or '' — rule matching and UI display."""
    try:
        return (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _rule_match(activity, projects, rules):
    bundle = (activity.get("app_bundle") or "").lower()
    title = (activity.get("title") or "").lower()
    domain = url_domain(activity.get("url"))
    by_id = {p["id"]: p for p in projects}
    for r in rules:
        kind, pat = r["kind"], (r["pattern"] or "").lower()
        if not pat:
            continue
        hit = (
            (kind == "app" and pat == bundle)
            or (kind == "url_domain" and domain and (domain == pat or domain.endswith("." + pat)))
            or (kind in ("title_contains", "phone", "contact") and pat in title)
        )
        if hit:
            return by_id.get(r["project_id"])
    return None


def resolve(activity, projects, rules, folders):
    """Return (project_id_or_None, confidence, reason)."""
    pid = _folder_match(activity.get("file_path"), folders)
    if pid is not None:
        return pid, "auto-file", os.path.basename(activity["file_path"])
    p = _rule_match(activity, projects, rules)
    if p:
        return p["id"], "auto-rule", "rule"
    return None, "unassigned", "no match"
