"""Refresh the auto-generated sections of the profile README.

Rewrites the text between these marker pairs in the given README:
  <!-- PROJECTS:START --> ... <!-- PROJECTS:END -->   recently updated repos
  <!-- ACTIVITY:START --> ... <!-- ACTIVITY:END -->   recent public GitHub activity

A section whose markers are missing is added just above the "Connect with me"
heading (or at the end), so it can be moved anywhere in the README afterwards.

Usage: python3 scripts/update_readme.py path/to/README.md [--dry-run]
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import github_api as gh

MAX_PROJECTS = 6
MAX_ACTIVITY = 8
HEADINGS = {
    "PROJECTS": "<h3 align=\"left\">🚀 What I'm working on</h3>",
    "ACTIVITY": "<h3 align=\"left\">⚡ Recent GitHub activity</h3>",
}


def md(text):
    """Escape the characters that would break inline Markdown."""
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", " ".join((text or "").split()))


def day(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").strftime("%b %d").replace(" 0", " ")


def repo_link(full_name):
    owner, name = full_name.split("/", 1)
    label = name if owner == gh.USER else full_name
    return f"[{md(label)}](https://github.com/{full_name})"


def projects_section(repos):
    repos = [r for r in repos if not r["fork"] and not r["archived"] and r["full_name"] != gh.PROFILE_REPO]
    repos.sort(key=lambda r: r["pushed_at"] or "", reverse=True)
    lines = []
    for r in repos[:MAX_PROJECTS]:
        parts = [f"**{repo_link(r['full_name'])}**"]
        if r.get("description"):
            parts.append(md(r["description"]))
        meta = []
        if r.get("language"):
            meta.append(f"`{r['language']}`")
        if r.get("stargazers_count"):
            meta.append(f"⭐ {r['stargazers_count']}")
        line = "- " + " — ".join(parts)
        if meta:
            line += " · " + " · ".join(meta)
        lines.append(line)
    return lines or ["_No public projects yet — check back soon!_"]


def describe(event):
    """One Markdown line for an event, or None to skip it."""
    kind, p, repo = event["type"], event.get("payload") or {}, event["repo"]["name"]
    where = repo_link(repo)
    if kind == "PushEvent":
        return f"⬆️ Pushed to {where}"
    if kind == "CreateEvent" and p.get("ref_type") == "repository":
        return f"🎉 Created {where}"
    if kind == "PublicEvent":
        return f"🌍 Open-sourced {where}"
    if kind == "ForkEvent":
        return f"🍴 Forked {where}"
    if kind == "WatchEvent":
        return f"⭐ Starred {where}"
    if kind == "ReleaseEvent" and p.get("action") == "published":
        rel = p.get("release") or {}
        tag = md(rel.get("tag_name") or "a new version")
        url = rel.get("html_url") or f"https://github.com/{repo}/releases"
        return f"📦 Released [{tag}]({url}) of {where}"
    if kind in ("PullRequestEvent", "IssuesEvent"):
        item = p.get("pull_request") or p.get("issue") or {}
        number = item.get("number") or p.get("number")
        if not number:
            return None
        path = "pull" if kind == "PullRequestEvent" else "issues"
        title = f" {md(item['title'])}" if item.get("title") else ""
        link = f"[#{number}{title}](https://github.com/{repo}/{path}/{number})"
        noun = "PR" if kind == "PullRequestEvent" else "issue"
        action = p.get("action")
        if action == "opened":
            return f"{'🔀' if noun == 'PR' else '❗'} Opened {noun} {link} in {where}"
        if action in ("closed", "merged") and (item.get("merged") or item.get("merged_at") or action == "merged"):
            return f"✅ Merged PR {link} in {where}"
    return None


def activity_section(events):
    lines, last = [], None
    for event in events:
        if event["repo"]["name"] == gh.PROFILE_REPO:
            continue
        text = describe(event)
        if not text or text == last:  # collapse runs of identical events, e.g. many pushes
            continue
        last = text
        lines.append(f"- {text} — _{day(event['created_at'])}_")
        if len(lines) == MAX_ACTIVITY:
            break
    return lines or ["_No recent public activity._"]


def add_missing_section(readme, name):
    if f"<!-- {name}:START -->" in readme:
        return readme
    block = f"{HEADINGS[name]}\n\n<!-- {name}:START -->\n<!-- {name}:END -->\n\n"
    anchor = re.search(r"^.*Connect with me.*$", readme, re.M)
    if anchor:
        return readme[: anchor.start()] + block + readme[anchor.start() :]
    return readme.rstrip() + "\n\n" + block


def replace_section(readme, name, lines):
    readme = add_missing_section(readme, name)
    pattern = re.compile(rf"(<!-- {name}:START -->).*?(<!-- {name}:END -->)", re.S)
    body = "\n".join(lines)
    return pattern.sub(lambda m: f"{m.group(1)}\n\n{body}\n\n{m.group(2)}", readme, count=1)


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if len(args) != 1:
        sys.exit(__doc__)
    readme = Path(args[0])
    old = readme.read_text(encoding="utf-8")
    new = replace_section(old, "PROJECTS", projects_section(gh.public_repos()))
    new = replace_section(new, "ACTIVITY", activity_section(gh.public_events()))
    if new == old:
        print(f"{readme} is already up to date.")
    elif "--dry-run" in sys.argv:
        print(f"Dry run: {readme} would change to:\n")
        print(new)
    else:
        readme.write_text(new, encoding="utf-8")
        print(f"{readme} updated.")


if __name__ == "__main__":
    main()
