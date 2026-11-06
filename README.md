# lk — a local LinkedIn writing agent

Write certificate stories, post replies and comments in your own voice, using a model that
runs on your machine. Everything is drafted locally first; publishing goes through
LinkedIn's **official API** when you say so. No browser automation, no session cookies.

```
lk cert  →  "I failed the exam twice before this arrived."  →  lk publish
```

**What the agent does, end to end:** see [`WHAT-IT-DOES.md`](WHAT-IT-DOES.md).

## Why

Browser automation is what gets accounts restricted — the User Agreement forbids it, and
it fingerprints badly. The official API does the same job legally, so that is what this
uses. Drafts stay local, and nothing is published until you run `lk publish` and confirm.

## Install

```bash
# 1. the model runtime
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b          # ~4.7 GB, good on 8 GB RAM

# 2. this tool
cd ~/linkedin-agent
python3 -m pip install --user -r requirements.txt   # just `requests`
cp .env.example .env            # then edit your name/role
```

If `pip` refuses ("externally managed environment"), use a venv:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```

Smaller machine? `ollama pull llama3.2:3b` and set `LK_MODEL=llama3.2:3b` in `.env`.

No model at all? Everything still runs with `LK_MOCK=1` so you can see the output shape.

## Use it

`./bin/lk` works without installing. All commands:

| Command | What it does |
|---|---|
| `lk doctor [--live]` | check Ollama; `--live` proves the model actually loads |
| `lk model [name]` | show or switch the local model |
| `lk check [--live]` | one-pass health check of model, token, drafts, voice, feeds, queue |
| `lk cert --title "..." --issuer "..." --skills "..." --story "..."` | storytelling post for a certificate or badge |
| `lk post "topic" --angle "my take"` | any post |
| `lk reply --post post.txt --comment "their words" --author Sara` | reply to a comment, with a suggested reaction |
| `lk comment --post their_post.txt --angle "..."` | comment on someone else's post |
| `lk search "query"` | free web search (DuckDuckGo, no key) |
| `lk learn --file my_post.txt --note "blunt, short"` | teach it your voice |
| `lk style` | rewrite style rules from all saved examples |
| `lk list` / `lk show ID` / `lk copy ID` / `lk mark ID --status posted` | manage drafts |
| `lk safe ID` | audit a draft for ban/spam signals |
| `lk coach ID` | score a draft against storytelling beats and get fixes |
| `lk web` | open the local web UI (drafts, generate, coach, publish) |
| `lk brief "topic"` / `--url LINK` | research the public web into a post brief |
| `lk digest` | collect new articles from your RSS feeds |
| `lk watch --list/--add/--remove` | manage feeds |

Add `--search` to `post` or `cert` to research first. Add `--json` to see the raw fields.

## The web UI

```bash
./bin/lk web                    # opens http://127.0.0.1:8080 in your browser
./bin/lk web --port 8081 --no-open
./bin/lk web --host 0.0.0.0     # reachable from Windows / your network
```

If a Windows browser can't reach `127.0.0.1`, use `--host 0.0.0.0` and open the
`From Windows:` URL it prints. If the browser **downloads** the page instead of
showing it, you opened a file path or the wrong port — copy the printed URL into
the address bar. The startup self-check prints `HTTP 200` when the server is
answering correctly.

A local single-page interface over the same engine. Nothing is sent anywhere; the server
binds to `127.0.0.1` only and refuses cross-origin posts. If the port is taken it tries
8081-8090. Under WSL the browser may not launch by itself — open the printed URL by hand,
or `http://localhost:8080` from Windows.

**Left panel** — every draft, newest first, with status and length. **Right panel** — the
selected draft:

| Button | Same as |
|---|---|
| Generate | `lk post` / `lk cert`, then saves the draft |
| Save edit | rewrites the draft; safety re-audits automatically |
| Coach | `lk coach` — score, beats, fixes, optional rewrite |
| Copy | `lk copy` |
| Dry run | `lk publish --dry-run` — shows the API payload, posts nothing |
| Publish | `lk publish --yes` (asks for confirmation first) |
| Mark posted | `lk mark --status posted` |

Generation still takes 1-3 minutes on CPU; the button shows a spinner. Publishing from the
UI is a real post under your name, and it is blocked when the safety audit raises a HIGH
finding — fix the text first.

### The certificate workflow

```bash
./bin/lk cert \
  --title "AWS Certified Solutions Architect" \
  --issuer "Amazon Web Services" \
  --skills "VPC design, IAM, cost optimisation" \
  --story "Failed twice. Third time I built one small project a week instead of watching courses."
```

The model is told to use a five-beat story shape — hook, struggle, turn, proof, invite —
and to never write it as an announcement. It is explicitly told **not to invent failures
you did not mention**. If you leave `--story` empty it stays truthful and vague rather
than making something up.

Output goes to `drafts/<id>.txt` (paste-ready), plus a `.json` record.

### Teaching it your voice

The first posts will sound generic. Fix that in two steps:

```bash
./bin/lk learn --file examples/post1.txt --note "the one about the outage"
./bin/lk learn --text "Shipped a small thing today. It broke twice. The fix was one line."
./bin/lk style        # distills all examples into data/style.md
```

There are four ways to feed it, and the learning loop is what makes this useful:

| Command | What it teaches |
|---|---|
| `lk learn --dir ~/my-posts/` | every `.txt`/`.md` in a folder, one post per file |
| `lk learn --csv Posts.csv` | your own posts from a LinkedIn export — the best source for voice |
| `lk ref --text/--dir/--analyze` | other people's posts — **structure only**, never voice |
| `lk learn --bad --text "..."` | anti-examples: styles you never want |
| `lk edit <id>` | you edit a draft before posting; it records your version and learns from the diff |

The export route is the strong one: LinkedIn → Settings → Data privacy → Get a copy of
your data → download and unzip → `lk learn --csv path/to/Posts.csv`. That is 50-200 of
your real posts, in your real voice.

Then `lk style` distills everything into `data/style.md`, which is prepended to every
prompt. Your five most recent examples are also injected verbatim as few-shot guidance.

Practical guidance:

- **5 examples** is the minimum to notice a difference. 20-30 is where it gets good.
- Add examples of the *kind* of post you want more of. If you only feed technical posts,
  it will only write technical posts.
- After 100+ posts, prune. Old examples in a voice you have outgrown pull it backwards.
- `data/style.md` is plain text: delete rules you disagree with.
- Re-run `lk style` whenever you add more than a handful of examples.

### Story coach

Every post is a story or it is an announcement. The coach tells you which:

```bash
./bin/lk coach 20261029-1544            # score a saved draft
./bin/lk coach --file my_post.txt       # score a file
./bin/lk coach --text "..." --rewrite   # also get a rewritten version
```

```
Story score: 3/10  [######..............]  this is an announcement, not a story

  [ ] hook    Generic announcement, no specific hook.
  [ ] stakes  No risk or loss mentioned.
  [ ] turn    No concrete change or turning point.
  [ ] proof   No specific detail provided.
  [ ] invite  No invitation for the reader to respond.

Fix before posting
  1. Remove the announcement language and focus on a specific skill or project.
  2. Add a concrete example of a skill you gained.
  3. End with a question that invites the reader to share their own experience.
```

Five beats are checked: **hook, stakes, turn, proof, invite**. Every criticism quotes
your actual words, and fixes are instructions rather than "make it more engaging".

`--learn` saves the post as a voice example, so the loop is: write → coach → fix →
`lk edit` → learned. The coach reads your last two examples to calibrate, so it scores
you against your own standard, not a generic one.

### Research agent

Collected from RSS and news feeds — public sources only, no browser, no LinkedIn.

```bash
./bin/lk watch --list                                   # 7 feeds preloaded
./bin/lk watch --add https://example.com/feed/ --name Example
./bin/lk digest                                         # new items, last 48h
./bin/lk digest --hours 24 --top 6                      # narrower window, more per feed
```

Output is ranked by `LK_TOPICS` in `.env`, saved to `data/digest/`, and already-seen
links are skipped on the next run. Then pick one and turn it into a post:

```bash
./bin/lk brief --url "<link from the digest>"
./bin/lk post "<topic>" --brief latest
./bin/lk coach <draft id>
```

`lk brief --url` reads the article, pulls out facts with numbers, three angles and three
hook options, and saves a brief. Nothing is invented: if the source has no number, the
brief says so.

Daily loop, about ten minutes:

```
lk digest → pick something you actually have an opinion on → lk brief --url → lk post --brief
→ lk coach → fix → paste → lk mark <id> --status posted
```

### Learning from other people's posts (safely)

You can learn structure from posts that performed well — but **never** feed them as voice
examples, or the model will imitate their sentences and you will post them under your name.

```bash
./bin/lk ref --text "post text" --note "why it worked"   # one post
./bin/lk ref --dir ~/swipe-file/                         # a folder of .txt files
./bin/lk ref --analyze                                   # distil structure → data/reference.md
./bin/lk ref --list                                      # what's saved
```

Reference posts are stored separately in `data/reference.jsonl` and shown to the model as
*shape only*: hook formula, paragraph rhythm, where the proof sits, how it ends. The prompt
tells it explicitly not to learn voice from them.

Two safeguards:

- `lk safe` compares your draft against every reference post and raises **HIGH** if it
  shares an eight-word sequence with one — accidental copying gets caught before you paste.
- Keep the swipe file small (10-20 posts). More than that and the structural advice turns
  into mush.

**Collect them by hand.** Copy the post text from your feed into a file. Do not scrape
LinkedIn — that is the automation that gets accounts restricted, and it is exactly the
thing this tool exists to avoid.

### Replying to comments

```bash
./bin/lk reply --post drafts/2026....txt --comment "How long did you study?" --author "Sara"
```

It picks one of LinkedIn's six reactions (👍 like, 👏 celebrate, 🤝 support, ❤️ love,
💡 insightful, 😄 funny) and writes a 1-3 sentence reply that quotes a detail instead of
saying "Great post". Use `--comment -` to paste the comment from stdin.

## How it fits together

```
lk/cli.py        command line
lk/voice.py      style rules + example posts → system prompt
lk/posts.py      certificate stories, topic posts, output checks
lk/comments.py   replies, comments, reaction choice
lk/search.py     DuckDuckGo lookup for context
lk/learn.py      save examples, distil style
lk/store.py      drafts/ as JSON + txt
lk/llm.py        Ollama HTTP client, JSON extraction, mock mode
```

Everything the model returns is validated: `posts.warnings()` flags a hook over 12 words,
more than 5 hashtags, a post over 3000 characters, or any banned cliché. Those warnings
print under every draft.

## Publishing through the official API

Optional. Without it everything stays draft-only. With it, `lk publish` posts through
LinkedIn's sanctioned endpoints using the `w_member_social` scope — no cookies, no
browser, and nothing for LinkedIn to detect because it is the documented way to do this.

**One-time setup (about 10 minutes):**

1. Go to <https://www.linkedin.com/developers/apps> → **Create app**. LinkedIn requires a
   LinkedIn Page to attach it to; if you have none, create a free one first.
2. **Settings** tab → add the redirect URL exactly: `http://localhost:8765/callback`
3. **Products** tab → add **Share on LinkedIn** (self-serve, no review)
4. **Auth** tab → copy Client ID and Client Secret into `.env`
5. Run `lk connect` — your browser opens, you approve, the token is saved

Then:

```bash
lk whoami                           # account, token expiry, daily usage
lk publish <draft-id> --dry-run     # show the exact request body
lk publish <draft-id>               # asks you to type "publish"
lk publish --file post.txt --connections
```

Tokens last 60 days and are revocable at
<https://www.linkedin.com/psettings/permitted-services>. The tool caps itself at 120
requests/day; LinkedIn's limit is 150.

### Replies without bursts

```bash
lk reply --post drafts/xxx.txt --comment "how long did you study?" \
  --post-url "https://www.linkedin.com/feed/update/urn:li:activity:7123..." \
  --author "Sara"
```

That drafts a reply and puts it in the approval queue. **Nothing sends until you
approve it.** One reply per person per post — if Sara comments twice on the same
post, the second one is skipped.

```bash
lk queue                       # see pending, approved, sent
lk queue --approve q1731...    # approve one drafted reply
lk queue --reject  q1731...    # reject it (never sends)
lk queue --run                 # send approved items that are due
lk queue --loop                # keep it open; sends as each one comes due
```

Defaults, so the account stays quiet:

| Rail | Default | Change with |
|---|---|---|
| Approval required | on | `LK_REQUIRE_APPROVAL=0` |
| Max replies/day | 5 | `LK_MAX_REPLIES_PER_DAY` |
| Gap between replies | 360s + jitter | `LK_REPLY_SPACING_S` |
| Quiet hours | 22:00–08:00 | `LK_QUIET_START` / `LK_QUIET_END` |

### The inbox (comments)

```bash
lk inbox --once     # check your recent posts for new comments, draft replies
lk inbox            # keep checking every 15 minutes (LK_WATCH_POLL_S)
```

In the web UI, open **Pending replies**. You can paste a comment there, draft a
reply, and approve it in one screen.

Reading comments needs a LinkedIn product your app may not have. If it is
missing, `lk inbox` says exactly what LinkedIn returned (403 / partner API) and
stops. Posting and replying still work; only automatic *reading* is blocked.

### Profile updates

There is **no API** for editing headline, About or Experience. `lk profile` writes the
copy; you paste it into the three fields, about a minute of work:

```bash
lk profile --cert "AWS Certified Security" --issuer AWS \
  --skills "incident response, IAM" \
  --achievement "passed second attempt, built a CloudTrail detection lab"
```

It returns a headline under 220 characters, a three-paragraph About, and one experience
bullet, and flags clichés like "robust" or "leveraging".

### What the API cannot do

| Task | Status |
|---|---|
| Post to your own profile | yes |
| Comment / reply as you | yes, with the post or comment URL |
| Edit profile | no API exists |
| Read your feed, others' posts, or who liked something | no API |
| Company page posting | partner programme only |

## What not to build

Anything that drives linkedin.com with a real or copied session cookie. It is against the
User Agreement, it fingerprints badly (endpoint mix, missing page telemetry, metronomic
timing), and a copied `li_at` is full account access that you cannot revoke except by
changing your password.

## Staying unbanned

The tool never touches LinkedIn. There is no login, no cookie, no browser, no API call —
`grep -rn linkedin --include=*.py .` returns nothing, and the only hosts in the code are
your local Ollama and DuckDuckGo. You paste by hand, which looks exactly like typing.

What actually gets accounts restricted is behavior, not AI text. `lk safe` checks a draft
for the patterns that matter, and runs automatically after every generation:

| Check | Why it matters |
|---|---|
| near-duplicate of an earlier draft (≥85% similar) | reposting the same text is the #1 spam signal |
| the same reply sent to multiple people | flags comment automation instantly |
| more than 2 posts marked posted in 24h | human posting rate is about one per day |
| more than ~12 comments marked in 24h | comment volume is what gets flagged fastest |
| links in the body | links get reach-throttled; put them in the first comment |
| more than 3 @mentions | mass tagging reads as engagement bait |
| hashtags over 5, or tags LinkedIn cannot parse (`#Security+`) | broken tags look bot-generated |
| AI tells ("delve into", "it's not just about") | reads as generated |
| leaked model artifacts | broken output looks automated |

Rules of thumb that keep you safe regardless of tooling:

- One post a day at most. Two on a launch day is fine; a week of two-a-day is not.
- Never send the same comment to several people. `lk reply` gives you a fresh one each time.
- Comment on posts you actually read. Ten thoughtful comments beat a hundred generic ones.
- Don't accept connection requests in bursts and don't automate invites.
- If LinkedIn ever asks you to verify identity or shows a warning banner, stop for a week.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot reach Ollama` | `ollama serve`, then `lk doctor` |
| Browser downloads the page instead of showing it | you opened a file or wrong port — copy the exact `lk web` URL into the address bar; use `--host 0.0.0.0` under WSL |
| `Model 'x' is not installed` | `ollama pull x` |
| `llama-server binary not found` | interrupted Ollama upgrade — re-run `curl -fsSL https://ollama.com/install.sh \| sh`, then `lk doctor --live` |
| `doctor` says ready but generation fails | run `lk doctor --live`; the plain check only proves the model is downloaded |
| Output is too formal | add 5 examples with `lk learn`, run `lk style` |
| JSON parse error | re-run; smaller models occasionally drift. A 7B+ model is more reliable |
| Search returns nothing | DuckDuckGo rate limit — wait a minute or drop `--search` |
