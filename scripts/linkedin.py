"""LinkedIn autopilot: publish queued posts and announce new GitHub projects.

Commands:
  run    Draft an announcement for each new public repo, then publish the next due
         post from linkedin/queue/ (at most one post per run).
  post   Publish the text in $POST_TEXT right away.

Add --dry-run (or set DRY_RUN=1) to print what would happen without posting or
changing any files.

Environment:
  LINKEDIN_ACCESS_TOKEN  member token with the openid, profile and w_member_social scopes
  LINKEDIN_PERSON_URN    optional, e.g. urn:li:person:AbC123 (looked up from the token if unset)
  LINKEDIN_API_VERSION   optional YYYYMM Posts API version (recent versions are tried if unset)
  TIMEZONE               IANA time zone for publish_on dates (default Asia/Kolkata)
  ANNOUNCE_DELAY_DAYS    days between drafting a new-project post and publishing it (default 1)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import github_api as gh

ROOT = Path(__file__).resolve().parent.parent / "linkedin"
QUEUE = ROOT / "queue"
PUBLISHED = ROOT / "published"
STATE = ROOT / "state.json"

TZ = ZoneInfo(os.environ.get("TIMEZONE") or "Asia/Kolkata")
ANNOUNCE_DELAY = int(os.environ.get("ANNOUNCE_DELAY_DAYS") or 1)
DRY_RUN = "--dry-run" in sys.argv or os.environ.get("DRY_RUN") == "1"
MAX_LENGTH = 3000  # LinkedIn's limit for post text

# Posts API "commentary" uses LinkedIn's little text format: these characters are
# markup and must be backslash-escaped, or the post can be silently cut off.
RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")
# URLs are passed through escaped as-is; #hashtags elsewhere become real hashtags.
TOKEN = re.compile(r"(?P<url>https?://\S+)|(?<![\w&#])#(?P<tag>[^\W_]+)(?!\w)")


def little_text(text):
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        out.append(RESERVED.sub(r"\\\1", text[pos : m.start()]))
        out.append(RESERVED.sub(r"\\\1", m["url"]) if m["url"] else "{hashtag|\\#|%s}" % m["tag"])
        pos = m.end()
    out.append(RESERVED.sub(r"\\\1", text[pos:]))
    return "".join(out)


# --- LinkedIn API ------------------------------------------------------------


def linkedin(method, url, token, body=None, version=None):
    headers = {"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0"}
    if version:
        headers["LinkedIn-Version"] = version
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read().decode(errors="replace")


def api_error(status, body):
    hint = {
        401: "The LinkedIn token is invalid or expired (they last 60 days). Generate a new one and "
        "update the LINKEDIN_ACCESS_TOKEN secret - see README.md.",
        403: "The token is missing a scope. Regenerate it with openid, profile and w_member_social.",
    }.get(status, "")
    sys.exit(f"LinkedIn API error {status}: {body}\n{hint}".rstrip())


def person_urn(token):
    if os.environ.get("LINKEDIN_PERSON_URN"):
        return os.environ["LINKEDIN_PERSON_URN"]
    status, _, body = linkedin("GET", "https://api.linkedin.com/v2/userinfo", token)
    if status != 200:
        api_error(status, body)
    return "urn:li:person:" + json.loads(body)["sub"]


def api_versions():
    """The YYYYMM versions to try: the configured one, else the last 12 months."""
    if os.environ.get("LINKEDIN_API_VERSION"):
        return [os.environ["LINKEDIN_API_VERSION"]]
    now = datetime.now(TZ)
    year, month = now.year, now.month
    versions = []
    for _ in range(12):
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        versions.append(f"{year}{month:02d}")
    return versions


def publish(text, token):
    """Post text to LinkedIn and return the post's URL."""
    if DRY_RUN:
        print(f"Dry run: would post to LinkedIn:\n---\n{text}\n---")
        return None
    body = {
        "author": person_urn(token),
        "commentary": little_text(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    for version in api_versions():
        status, headers, resp = linkedin("POST", "https://api.linkedin.com/rest/posts", token, body, version)
        if status == 201:
            urn = headers.get("x-restli-id")
            url = f"https://www.linkedin.com/feed/update/{urn}/" if urn else "https://www.linkedin.com/feed/"
            print(f"Posted to LinkedIn: {url}")
            return url
        if status in (400, 426) and "version" in resp.lower():
            continue  # that API version isn't live (yet or any more); nothing was posted, try an older one
        api_error(status, resp)
    sys.exit("No active LinkedIn API version found. Set the LINKEDIN_API_VERSION variable (YYYYMM).")


# --- Post files ----------------------------------------------------------------


def read_post(path):
    """Parse a post file: optional `key: value` front matter between --- lines, then the text."""
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n") + "\n"
    meta, body = {}, raw
    if raw.startswith("---\n"):
        header, sep, rest = raw[4:].partition("\n---\n")
        if sep:
            body = rest
            for line in header.splitlines():
                key, colon, value = line.partition(":")
                if colon:
                    meta[key.strip()] = value.strip()
    return meta, body.strip()


def write_post(path, meta, body):
    header = "".join(f"{key}: {value}\n" for key, value in meta.items())
    path.write_text(f"---\n{header}---\n\n{body}\n", encoding="utf-8")


def load_queue():
    """All queued posts as (publish_on, path, meta, text), oldest first. Exits if any is invalid."""
    posts, errors = [], []
    for path in sorted(QUEUE.glob("*.md")):
        meta, text = read_post(path)
        try:
            when = date.fromisoformat(meta["publish_on"]) if meta.get("publish_on") else date.min
        except ValueError:
            errors.append(f"{path.name}: publish_on must look like 2026-10-31, not {meta['publish_on']!r}")
            continue
        if not text:
            errors.append(f"{path.name}: the post text is empty")
        elif len(text) > MAX_LENGTH:
            errors.append(f"{path.name}: the post is {len(text)} characters; LinkedIn allows {MAX_LENGTH}")
        else:
            posts.append((when, path, meta, text))
    if errors:
        sys.exit("Fix these posts in linkedin/queue/:\n  " + "\n  ".join(errors))
    return sorted(posts, key=lambda p: (p[0], p[1].name))


def save(path, write):
    if DRY_RUN:
        print(f"Dry run: would write {path.relative_to(ROOT.parent)}")
    else:
        write()


# --- New project announcements ----------------------------------------------


def hashtag(topic):
    return "#" + "".join(part.capitalize() for part in re.split(r"[-_]", topic))


def announcement(repo):
    lines = [f"🚀 New project on GitHub: {repo['name']}", "", repo["description"].strip()]
    if repo.get("language"):
        lines += ["", f"Built with {repo['language']}."]
    lines += ["", f"Check it out 👉 {repo['html_url']}"]
    tags = [hashtag(t) for t in (repo.get("topics") or [])[:3]] + ["#GitHub", "#OpenSource"]
    lines += ["", " ".join(dict.fromkeys(tags))]
    return "\n".join(lines)


def announce_new_repos(known, today):
    """Queue a post for every public repo not seen before. Returns the updated set of known repos."""
    known = set(known)
    for repo in gh.public_repos():
        name = repo["full_name"]
        if name in known or repo["fork"] or name == gh.PROFILE_REPO:
            continue
        if not (repo.get("description") or "").strip():
            print(f"{name} has no description yet; it will be announced once it gets one.")
            continue
        known.add(name)
        publish_on = today + timedelta(days=ANNOUNCE_DELAY)
        path = QUEUE / f"{publish_on}-{repo['name']}.md"
        meta, text = {"publish_on": publish_on.isoformat(), "repo": name}, announcement(repo)
        print(f"New project {name}: drafted {path.name} for {publish_on}.")
        if not DRY_RUN:
            try:
                meta["issue"] = gh.open_issue(
                    f"LinkedIn post about {repo['name']} goes out on {publish_on:%b %d}",
                    f"I drafted a LinkedIn post announcing **{name}**. It will be published automatically on "
                    f"**{publish_on:%A, %b %d}**.\n\n"
                    f"- To change the wording, edit `linkedin/queue/{path.name}`.\n"
                    f"- To cancel, delete that file and close this issue.\n\n"
                    "Draft:\n\n" + "\n".join(f"> {line}" for line in text.splitlines()),
                )
            except Exception as err:  # the draft still gets queued; the issue is just a heads-up
                print(f"::warning::Could not open a heads-up issue for {name}: {err}")
        save(path, lambda: write_post(path, meta, text))
    return known


# --- Commands -----------------------------------------------------------------


def published_path(name):
    PUBLISHED.mkdir(exist_ok=True)
    return PUBLISHED / name


def cmd_run(token):
    today = datetime.now(TZ).date()
    if STATE.exists():
        known = json.loads(STATE.read_text())["known_repos"]
        updated = announce_new_repos(known, today)
    else:
        known, updated = None, sorted(r["full_name"] for r in gh.public_repos())
        print(f"First run: remembering your {len(updated)} existing repos so only new ones get announced.")
    if known is None or set(updated) != set(known):
        save(STATE, lambda: STATE.write_text(json.dumps({"known_repos": sorted(updated)}, indent=2) + "\n"))

    due = [post for post in load_queue() if post[0] <= today]
    if not due:
        print("No posts are due today.")
        return
    _, path, meta, text = due[0]
    print(f"Publishing {path.name}")
    url = publish(text, token)
    if DRY_RUN:
        return
    meta.update(posted_at=datetime.now(TZ).isoformat(timespec="minutes"), post_url=url)
    write_post(published_path(path.name), meta, text)
    path.unlink()
    if meta.get("issue"):
        try:
            gh.close_issue(int(meta["issue"]), f"Posted to LinkedIn: {url}")
        except Exception as err:
            print(f"::warning::Posted, but could not close issue #{meta['issue']}: {err}")
    if len(due) > 1:
        print(f"{len(due) - 1} more due post(s) will go out on the next runs (one post per run).")


def cmd_post(token):
    text = (os.environ.get("POST_TEXT") or "").strip()
    if not text:
        sys.exit("POST_TEXT is empty.")
    if len(text) > MAX_LENGTH:
        sys.exit(f"The post is {len(text)} characters; LinkedIn allows {MAX_LENGTH}.")
    url = publish(text, token)
    if not DRY_RUN:
        now = datetime.now(TZ)
        meta = {"posted_at": now.isoformat(timespec="minutes"), "post_url": url}
        write_post(published_path(f"{now:%Y-%m-%d-%H%M}-manual.md"), meta, text)


def main():
    command = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    if command not in ("run", "post"):
        sys.exit(__doc__)
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token and not DRY_RUN:
        print("::warning::LINKEDIN_ACCESS_TOKEN is not set, so nothing was posted. See README.md for setup.")
        return
    if command == "run":
        cmd_run(token)
    else:
        cmd_post(token)


if __name__ == "__main__":
    main()
