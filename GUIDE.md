# lk — complete guide

A local LinkedIn writing agent. Runs on your machine with Ollama, drafts in your voice,
publishes through LinkedIn's official API, and never touches a browser session.

```
~/linkedin-agent
├── bin/lk              launcher (no install needed)
├── lk/                 19 modules, ~3,550 lines (cli, web UI, engine, safety)
├── data/               your voice, feeds, briefs, token
├── drafts/             every generated draft (json + txt)
├── .env                model, name, LinkedIn credentials
└── README.md           shorter reference
```

## Status right now

| Item | State |
|---|---|
| Model | `qwen2.5:7b` installed and running |
| LinkedIn | connected as **Jan Attallah**, `urn:li:person:IyOxB-Nvdd` |
| Token | valid, verified live (expires ~2026-12-30) |
| Voice examples | **0 saved** — this is the gap |
| Requests used | 0 / 120 today |

---

# Command catalogue

28 commands, grouped by what they do.

## 0. Web UI

### `lk web` — the same engine, in a browser
```bash
lk web                    # http://127.0.0.1:8080, opens automatically
lk web --port 8081        # different port
lk web --no-open          # don't launch a browser
lk web --host 0.0.0.0     # reachable from Windows / your network
```

Local only: binds to `127.0.0.1`, no external requests, rejects cross-origin POSTs.
Left side lists every draft; right side shows the text with buttons for **Save edit**,
**Coach**, **Copy**, **Mark posted**, **Dry run** and **Publish**. **+ New draft** generates
a topic post or a certificate story through the same model prompt as the CLI.

Generated drafts appear here immediately because both interfaces read `drafts/`. Publish
is still a real post under your name and is refused if the safety audit finds a HIGH issue.
Ctrl+C in the terminal stops the server.

## 1. Writing

### `lk cert` — certificate or badge story
```bash
lk cert --title "CompTIA Security+" \
        --issuer "CompTIA" \
        --skills "threat analysis, incident response" \
        --story "Failed the first attempt. Second time I built a home lab." \
        --tone "dry, no emoji"
```
Five-beat structure: hook → struggle → turn → proof → invite. It is forbidden from
inventing failures you did not mention, and refuses to open with "I'm thrilled to announce".

| Flag | Meaning |
|---|---|
| `--title` | certificate name (required) |
| `--issuer` | who issued it |
| `--skills` | comma separated |
| `--story` | what really happened — **the thing that makes it good** |
| `--tone` | e.g. `honest`, `funny`, `no emoji` |
| `--search` | look the certificate up first |
| `--json` | also print raw fields |
| `--no-save` | don't write a draft |

### `lk post` — any topic
```bash
lk post "why I stopped collecting certificates" --angle "the lab mattered more"
lk post "DDoS trends" --brief latest        # use a researched brief
lk post "zero trust" --search               # quick web context
```

### `lk comment` — comment on someone else's post
```bash
lk comment --post their_post.txt --angle "we cut rollback time in half"
```

### `lk reply` — reply to a comment on your post
```bash
lk reply --post drafts/xxx.txt --comment "how long did you study?" --author Sara
lk reply --post drafts/xxx.txt --comment "..." --post-url "https://linkedin.com/feed/update/urn:li:activity:7123..." 
lk reply ... --send              # post immediately
lk reply ... --delay 15m         # spacing when queueing
```
Returns a suggested reaction (👍 like, 👏 celebrate, 🤝 support, ❤️ love, 💡 insightful,
😄 funny) plus a reply that quotes a detail instead of saying "Great post".

---

## 2. Coaching

### `lk coach` — score a draft against storytelling beats
```bash
lk coach 20261029-180244               # by draft id
lk coach --file my_post.txt
lk coach --text "..." --rewrite        # include a rewritten version
lk coach --file f.txt --learn          # save it as a voice example
```
Scores 0-10 on **hook, stakes, turn, proof, invite**, quotes the exact weak line, and
gives 2-4 actionable fixes. Reads your last two examples to calibrate to your standard.

---

## 3. Research

### `lk digest` — new articles from your feeds
```bash
lk digest                      # last 48h, 4 per feed
lk digest --hours 24 --top 6
lk digest --all                # include already-seen items
```
7 feeds preloaded (Krebs, BleepingComputer, The Hacker News, Cloudflare, AWS Security,
Microsoft Security, Schneier). Ranked by `LK_TOPICS` in `.env`. Saves to `data/digest/`.

### `lk watch` — manage feeds
```bash
lk watch --list
lk watch --add https://example.com/feed/ --name Example
lk watch --remove Example
```

### `lk brief` — turn an article into facts, angles, hooks
```bash
lk brief "phishing resistant MFA"
lk brief --url "https://blog.example.com/post"     # one specific article
lk brief --show latest
```
Reads the page, extracts 5-8 facts with numbers, 3 angles, 3 hooks. Never invents numbers.

### `lk search` — plain web search
```bash
lk search "linkedin posts api limits" --limit 5
```

---

## 4. Teaching it your voice

### `lk learn` — add examples
```bash
lk learn --file post.txt --note "blunt, no ending"
lk learn --dir ~/my-posts/                       # every .txt/.md
lk learn --csv ~/Downloads/.../Shares.csv        # LinkedIn export
lk learn --bad --text "I'm thrilled to announce..." --note "LinkedIn parody"
```
| File | Purpose |
|---|---|
| `data/examples.jsonl` | your posts → voice |
| `data/avoid.jsonl` | anti-examples → never write like this |
| `data/style.md` | distilled rules, prepended to every prompt |

### `lk style` — rewrite the rules from all examples
```bash
lk style
```

### `lk edit` — record what you actually posted
```bash
lk edit <id>                  # opens $EDITOR
lk edit <id> --file final.txt
lk edit <id> --no-learn       # update only, don't learn it
```
The highest-value loop: generate → edit → it learns your version.

### `lk ref` — structure from other people's posts (never voice)
```bash
lk ref --text "..." --note "why it worked"
lk ref --dir ~/swipe-file/
lk ref --analyze          # distil structure → data/reference.md
lk ref --list
```
Shown to the model as *shape only*. `lk safe` fails your draft if it copies 8+ consecutive
words from a reference.

---

## 5. Publishing

### `lk connect` — authorise the API
```bash
lk connect                # opens browser
lk connect --manual       # prints URL, paste the redirect back (use in WSL)
lk whoami                 # verify
lk disconnect             # delete local token
```
OAuth with `openid profile w_member_social`. Token stored in `data/auth.json` (mode 600).
Revoke any time: <https://www.linkedin.com/psettings/permitted-services>

### `lk publish` — post it
```bash
lk publish <id>                  # shows text, asks you to type "publish"
lk publish <id> --dry-run        # shows the API payload, posts nothing
lk publish --file post.txt --connections
lk publish <id> --yes            # skip the prompt
lk publish <id> --force          # override a HIGH safety flag
```

### `lk queue` — spaced replies with approval
```bash
lk queue                       # what's waiting and when
lk queue --approve q123        # approve a drafted reply
lk queue --reject  q123        # reject it (never sends)
lk queue --run                 # send approved items that are due
lk queue --loop                # keep open, send as they come due
lk queue --cancel q123
```
Nothing sends until you approve it. One reply per person per post. Defaults:
5 replies/day, 6-minute gap plus jitter, no sends between 22:00 and 08:00.

### `lk inbox` — comments
```bash
lk inbox --once     # check recent posts for new comments, draft replies
lk inbox            # check every 15 minutes
```
Drafts land in the approval queue. Reading comments needs a LinkedIn product the
posting-only app may not have; if it is missing, `lk inbox` prints the exact API
error and stops. You can always paste a comment in the web UI instead.

### `lk profile` — headline and About after an achievement
```bash
lk profile --cert "AWS Certified Security" --issuer AWS \
           --skills "incident response, IAM" \
           --achievement "passed second attempt, built a CloudTrail lab"
```
Returns a headline (<220 chars), a 3-paragraph About, and one experience bullet. **You
paste it** — LinkedIn has no profile write API.

---

## 6. Drafts

```bash
lk list                       # all drafts
lk list --status draft        # unposted only
lk show <id>                  # print it
lk copy <id>                  # clipboard (needs xclip)
lk mark <id> --status posted  # keep volume tracking honest
```

## 7. Model

### `lk model` — see or switch the local model
```bash
lk model                        # current model + everything installed
lk model qwen2.5-coder:7b       # switch (writes LK_MODEL to .env)
lk doctor --live                # prove the new one actually loads
```
Switching is one line in `.env`, but this checks the model is installed first.
`lk model` does not download anything — `ollama pull <name>` does.

| Model | Best for |
|---|---|
| `qwen2.5:7b` | writing posts (current default) |
| `qwen2.5-coder:7b` | editing code and files in an agent harness |
| `qwen3:8b` | harder reasoning, slower |
| anything bigger than 8B | needs more than 8 GB of RAM |

### `lk check` — every subsystem in one pass
```bash
lk check            # fast: model installed, token valid, drafts, voice, feeds, queue
lk check --live     # also loads the model to prove a real generation will run
```
Exit code 1 if something is broken. This is the first command to run when anything
mislabels — it names the failing piece and the command that fixes it.

## 8. Safety

### `lk safe` — spam and ban signals
```bash
lk safe <id>          # default: newest draft
```
Runs automatically after every generation. Checks:

| Check | Level |
|---|---|
| ≥85% identical to an earlier draft | HIGH |
| same reply already sent to someone else | HIGH |
| >2 posts marked posted in 24h | HIGH |
| >3000 characters | HIGH |
| leaked model artifacts (random digits) | HIGH |
| copies 8+ words from a reference post | HIGH |
| links in the body, >3 mentions | MEDIUM |
| >5 hashtags, unparseable tags | MEDIUM |
| AI-tell phrases | MEDIUM |
| >2 emoji, >1 question | LOW |

---

# Workflows

## First time (do this now)
```bash
cd ~/linkedin-agent
lk learn --file post1.txt --note "..."      # ×5 real posts
lk style
cat data/style.md                            # read what it inferred
```

## Daily, 10 minutes
```bash
lk digest
lk brief --url "<link you care about>"
lk post "<topic>" --brief latest
lk coach <id>
lk edit <id>                                 # fix it in your words
lk publish <id>
```

The same loop in a browser: `lk web`, then **+ New draft → Generate → Coach → edit → Publish**.
Use whichever is less friction; they share `drafts/` and `data/`.

## When you earn a certificate
```bash
lk cert --title "..." --story "what actually happened"
lk coach <id>
lk publish <id>
lk profile --cert "..."                      # paste the new headline/About
```

## When someone comments
```bash
lk reply --post drafts/xxx.txt --comment "their words" --author "Name" \
         --post-url "https://www.linkedin.com/feed/update/urn:li:activity:..."
# reply is drafted; nothing sends yet
lk queue --approve q123                      # approve it
lk queue --loop                              # leave running, or lk queue --run later
```

---

# Files that matter

| Path | Contents |
|---|---|
| `.env` | model, your name/role, `LK_TOPICS`, LinkedIn credentials |
| `data/examples.jsonl` | your voice examples |
| `data/avoid.jsonl` | anti-examples |
| `data/style.md` | distilled voice rules — edit by hand freely |
| `data/reference.jsonl` | other people's posts (structure only) |
| `data/reference.md` | distilled structural patterns |
| `data/feeds.json` | RSS feeds |
| `data/briefs/` | research briefs |
| `data/digest/` | daily digests |
| `data/auth.json` | OAuth token, mode 600 — **never commit** |
| `drafts/*.txt` | paste-ready posts |
| `drafts/*.json` | structured record + metadata |

---

# Limits, honestly

| Thing | Reality |
|---|---|
| Model speed | 30s-3min per generation on 4 CPU cores; first call after start is slowest |
| Context | 4096 tokens; only the last 5 examples fit, `style.md` carries the rest |
| Cold start | 0 examples = generic voice. 5 changes it, 20-30 is where it gets good |
| Profile edits | no API — `lk profile` writes, you paste |
| Reading LinkedIn | no API for feeds, others' posts, or who liked something |
| Comments | you need the post/comment URL; parsing works for both |
| Token | 60 days, no refresh token issued; reconnect with `lk connect --manual` |
| Daily cap | tool stops at 120 requests; LinkedIn allows 150 |
| Company pages | partner programme only, not available self-serve |

# Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot reach Ollama` | `ollama serve`, then `lk doctor` |
| Browser downloads the page instead of showing it | you opened a file or wrong port — copy the exact `lk web` URL into the address bar; use `--host 0.0.0.0` under WSL |
| `Model 'x' is not installed` | `ollama pull x` |
| `llama-server binary not found` | interrupted Ollama upgrade — `curl -fsSL https://ollama.com/install.sh \| sh`, then `lk doctor --live` |
| `lk doctor` says ready but generation fails | run `lk doctor --live`; the plain check only lists models |
| `token expired or revoked` | `lk connect --manual` |
| `unauthorized_scope_error` | add *Sign In with LinkedIn using OpenID Connect* product |
| redirect shows "site can't be reached" | expected — copy the URL from the address bar, paste at the prompt |
| `invalid authorization code` | the code expired; re-run `lk connect --manual` |
| output too formal | `lk learn` five posts, then `lk style` |
| JSON parse error | re-run; 7B models occasionally drift |
| search returns nothing | DuckDuckGo rate limit; wait a minute |

# Rules that keep the account safe

1. One post per day. Mark each one posted.
2. Never reuse a comment across people.
3. Comment only on posts you actually read.
4. Links go in the first comment, not the body.
5. If LinkedIn shows a warning banner, stop for a week.
6. Never drive linkedin.com with a session cookie — that is what got the account restricted before.
