# Automate

GitHub Actions that keep my [GitHub profile](https://github.com/zensharma0512-a11y) fresh and post to LinkedIn for me.

| Workflow | What it does | When |
| --- | --- | --- |
| **Update profile README** | Rewrites the *What I'm working on* and *Recent GitHub activity* sections of my profile README | Every 6 hours |
| **LinkedIn autopilot** | Publishes posts from `linkedin/queue/` and drafts an announcement for every new public repo | Daily at 09:53 IST, and whenever a post is pushed to the queue |

Everything is plain Python (standard library only), so there is nothing to install.

> [!NOTE]
> This repo is public, so anyone can read queued posts before they go out. Also, GitHub pauses scheduled workflows in a public repo after 60 days without any commits; it emails you first, and one click on **Actions** turns them back on. Making the repo private avoids both, and these jobs use only a small share of the free Actions minutes for private repos.

## Setup

### 1. Let the README workflow push to the profile repo

1. Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new):
   - **Repository access:** Only select repositories → `zensharma0512-a11y`
   - **Permissions → Repository permissions → Contents:** Read and write
2. In this repo go to **Settings → Secrets and variables → Actions → New repository secret**, name it `PROFILE_REPO_TOKEN` and paste the token.
3. Go to **Actions → Update profile README → Run workflow**.

The first run adds the two sections just above *Connect with me* in the profile README. You can move them anywhere you like, as long as you keep the `<!-- PROJECTS:START -->`-style markers.

### 2. Connect LinkedIn

1. Create an app at <https://www.linkedin.com/developers/apps/new>. LinkedIn asks you to link a LinkedIn Page to the app; if you don't have one, create a simple page (for example, for your projects) first.
2. On the app's **Products** tab, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**. Both are self-serve.
3. Open the [OAuth token generator](https://www.linkedin.com/developers/tools/oauth/token-generator), pick your app, tick `openid`, `profile` and `w_member_social`, and sign in. If it complains about the redirect URL, add `https://www.linkedin.com/developers/tools/oauth/redirect` under the app's **Auth** tab and try again.
4. Save the token as a repository secret named `LINKEDIN_ACCESS_TOKEN`.
5. Check it works: **Actions → LinkedIn autopilot → Run workflow**, type a test message and tick **Dry run**.

> [!IMPORTANT]
> LinkedIn tokens expire after **60 days**. When that happens, the workflow fails and says so (GitHub emails you). Repeat steps 3 and 4. Posts that come due in the meantime wait in the queue and go out on the next run after you update the token.

## Writing posts

Add a Markdown file to `linkedin/queue/`. You can do this from the GitHub website or app (**Add file → Create new file**):

```markdown
---
publish_on: 2026-10-20
---

Finally got my robot arm tracking objects in real time using OpenCV and ROS 2 🤖

Biggest lesson: calibrate the camera before blaming the code.

#Robotics #ComputerVision
```

- `publish_on` is optional. Without it, the post goes out on the next run. Pushing a file starts a run, so a post that is due is published within a minute or two.
- **One post per run.** If several posts are due, the rest go out on the following days.
- Just write plain text. `#hashtags` become real hashtags, and characters LinkedIn treats specially, such as `( ) * _ @`, are escaped for you. The limit is 3,000 characters.
- After posting, the file moves to `linkedin/published/` with a link to the post.

To post straight away without a file: **Actions → LinkedIn autopilot → Run workflow**, then type the text.

## New project announcements

When a new public repo shows up on my account, the bot:

1. drafts a post in `linkedin/queue/` scheduled for **tomorrow**, using the repo's description, language and topics (topics become hashtags), and
2. opens an issue in this repo, so you get a notification.

To change the wording, edit the draft. To cancel, delete the file and close the issue.

- Forks are never announced.
- Repos without a description are skipped until they get one, so scratch repos stay quiet.
- On its first run the bot only records the repos that already exist; it doesn't announce them.

## Optional settings

Add these under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TIMEZONE` | `Asia/Kolkata` | Time zone used for `publish_on` dates |
| `ANNOUNCE_DELAY_DAYS` | `1` | Days between drafting a new-project post and publishing it |
| `LINKEDIN_API_VERSION` | auto | Pins a `YYYYMM` LinkedIn Posts API version instead of trying recent ones |
| `LINKEDIN_PERSON_URN` | auto | Your `urn:li:person:…` ID, which skips the profile lookup |

The schedules are the `cron` lines in `.github/workflows/`, written in UTC.

## Running locally

```sh
python3 scripts/update_readme.py path/to/README.md --dry-run
DRY_RUN=1 python3 scripts/linkedin.py run
```

Pull requests run both workflows in dry-run mode, so you can see what a change would do before merging it.

---

This uses only LinkedIn's official API, to publish your own posts. It doesn't scrape, auto-like or auto-connect; those break LinkedIn's terms and get accounts restricted.
