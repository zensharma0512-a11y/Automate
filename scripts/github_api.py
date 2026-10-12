"""Tiny GitHub REST client (stdlib only) shared by the automation scripts."""

import json
import os
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
USER = os.environ.get("PROFILE_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "zensharma0512-a11y"
PROFILE_REPO = f"{USER}/{USER}"
# The repo this automation runs in; issues about LinkedIn drafts are opened here.
THIS_REPO = os.environ.get("GITHUB_REPOSITORY", f"{USER}/Automate")


def request(method, path, body=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USER}-profile-automation",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def public_repos():
    """All public repos owned by USER, newest first."""
    repos, page = [], 1
    while True:
        batch = request("GET", f"/users/{USER}/repos?type=owner&sort=created&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def public_events():
    return request("GET", f"/users/{USER}/events/public?per_page=100")


def open_issue(title, body):
    return request("POST", f"/repos/{THIS_REPO}/issues", {"title": title, "body": body})["number"]


def close_issue(number, comment):
    request("POST", f"/repos/{THIS_REPO}/issues/{number}/comments", {"body": comment})
    request("PATCH", f"/repos/{THIS_REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})
