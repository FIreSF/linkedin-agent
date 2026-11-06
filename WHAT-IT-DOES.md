# What this agent does

A local LinkedIn writing agent. It runs on your own machine, uses a local model
(`qwen2.5:7b`), and talks to LinkedIn only through the official API.

**Nothing is posted automatically.** Every post and every reply waits for a human
action: `publish` asks you to confirm, and replies wait for explicit approval.

---

## 1. Research

| Command | What it does |
|---|---|
| `lk digest` | Collects new articles from the RSS/Atom feeds you added |
| `lk watch` | Manages those feeds (`--add`, `--list`, `--remove`) |
| `lk brief <topic>` | Reads public pages about a topic and writes a post brief |
| `lk search <query>` | One web lookup |
| `lk ref <file>` | Saves someone else's post as a **structure** reference only |

Your topics live in `.env` as `LK_TOPICS`, and matching articles rank first.

## 2. Writing

| Command | What it does |
|---|---|
| `lk post` | Drafts a post about a topic + your real story |
| `lk cert` | Drafts a certificate / badge story |
| `lk coach <id>` | Scores a draft against storytelling beats and flags weak spots |
| `lk humanize <id>` | Strips em dashes, invisible characters and filler words (no model) |
| `lk hooks` | Twenty-one opening-line formulas; `--apply <id> --formula "open loop"` rewrites the hook |
| `lk plan` | A week of suggestions: what to post, when, and what to engage with |
| `lk safe <id>` | Checks for spam and ban signals before you post |
| `lk profile` | Writes a new headline and About section for you to paste |

The voice comes from three places:

- `data/style.md` — the rules
- `data/examples.jsonl` — posts you liked (currently 4)
- `data/reference.jsonl` + `data/reference.md` — structure from other people

## 3. Learning

| Command | What it does |
|---|---|
| `lk learn --file/--dir/--csv/--text` | Teaches the agent from real posts |
| `lk learn --bad` | Saves an anti-example: a style it must avoid |
| `lk edit <id>` | Records what you *actually* posted and learns from your edit |
| `lk style` | Rewrites the style rules from your saved examples |

The correct loop is: the agent drafts, **you edit**, `lk edit` learns your version.
It does not learn from its own unedited output, because that makes it repeat
itself harder every cycle.

## 4. Publishing

| Command | What it does |
|---|---|
| `lk connect` | OAuth authorisation, token stored locally with mode 600 |
| `lk whoami` | Shows the account and today's usage |
| `lk publish <id>` | Posts a draft through the official API |
| `lk publish <id> --image p.png --alt "text"` | Posts with an image |
| `lk publish <id> --dry-run` | Shows the exact request body, posts nothing |
| `lk disconnect` | Deletes the local token |

Images use LinkedIn's real upload flow: `initializeUpload`, then upload the bytes,
then attach the returned `urn:li:image:...`. JPG, PNG and GIF, under 10 MB.

## 5. Replies and comments

| Command | What it does |
|---|---|
| `lk reply ...` | Drafts a reply to a comment on your post |
| `lk comment ...` | Drafts a comment on someone else's post |
| `lk inbox` | Checks your recent posts for new comments and drafts replies |
| `lk queue` | Shows the reply queue |
| `lk queue --approve <id>` | Approves a drafted reply |
| `lk queue --reject <id>` | Rejects it — never sends |
| `lk queue --run` | Sends approved replies that are due |
| `lk queue --loop` | Keeps running and sends as each one comes due |

### Reply rules built into the code

- **One reply per person per post.** A second comment from the same person on the
  same post is skipped. A different post is allowed.
- **Approval required.** A drafted reply has status `pending-approval` and cannot
  send until approved.
- **Maximum 5 replies per day.**
- **At least 6 minutes between replies**, plus random jitter, so sends never look
  clockwork.
- **Quiet hours 22:00–08:00.** Nothing sends at night.

All of these are configurable in `.env`.

## 6. The web UI

```bash
lk web                 # http://127.0.0.1:8080
lk web --host 0.0.0.0  # reachable from Windows / your network
```

- Draft list with status
- Generate a new draft
- Edit text, attach or remove an image with a preview
- **Humanize** — one click removes em dashes, invisible characters and filler words
- Coach, dry run, publish
- **Pending replies**: paste a comment, draft a reply, approve or reject

## 7. Health checks

| Command | What it does |
|---|---|
| `lk doctor` | Checks Ollama and that the model is installed |
| `lk doctor --live` | Also loads the model and asks it a question |
| `lk check` | One pass over every subsystem |
| `lk model` | Shows or switches the local model |
| `lk model qwen2.5-coder:7b` | Switches to the coder model for code/file work |

## 8. Safety defaults

- Official API only — no cookies, no scraping, no browser automation
- Token stored locally, chmod 600, revocable from LinkedIn settings
- 120 requests/day internal cap (LinkedIn allows 150)
- Writes to LinkedIn always pass a safety check first
- Anything flagged HIGH by `lk safe` blocks the publish unless you force it
- Replies never send without approval

## 9. What it cannot do

- **Read comments automatically** unless the LinkedIn app has the partner-level
  read product. Without it the API returns `403 ACCESS_DENIED`. The agent prints
  that exact error and stops; paste the comment in the web UI instead.
- **Edit your profile.** LinkedIn has no API for headline, About or Experience.
  `lk profile` writes the text; you paste it.
- **Work without Ollama.** The model must be running locally.
- **Guarantee you won't be banned.** It lowers the risk. It does not remove it.

## 10. The full loop

```
digest / brief      →  pick a topic
plan                →  what to post this week, and when
post / cert         →  draft in your voice
hooks --apply       →  rewrite the opening with a formula
humanize            →  strip em dashes, invisible chars, filler words
coach / safe        →  check it
you edit            →  lk edit learns your version
publish             →  official API, optional image
someone comments    →  lk inbox or paste in the web UI
lk queue --approve  →  you approve
lk queue --loop     →  sends 5/day max, 6 min apart, daytime only
```
