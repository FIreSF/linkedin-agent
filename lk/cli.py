"""Command line interface for the LinkedIn agent."""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from . import brief as brief_mod
from . import coach, comments, config, llm, posts, safety, search, store, voice

# ── helpers ──────────────────────────────────────────────────────────────


def _read(value: str) -> str:
    """Accept a file path, '-' for stdin, or literal text."""
    if value == "-":
        return sys.stdin.read()
    path = Path(value).expanduser()
    if path.is_file():
        return path.read_text()
    return value


def _emit(title: str, text: str, warnings: list[str], record: dict | None, raw) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 60 - len(title)))
    print()
    print(text)
    print()
    print(f"({len(text)} characters)")
    for warning in warnings:
        print(f"  ! {warning}")
    if record:
        safety.report(record)
        print(f"  saved: {record['id']}")
        print(f"  file : drafts/{record['id']}.txt")
    if raw is not None:
        print()
        print(json.dumps(raw, indent=2, ensure_ascii=False))


def _save(kind: str, title: str, text: str, meta: dict, no_save: bool):
    if no_save:
        return None
    return store.save(kind, title, text, meta)


# ── commands ─────────────────────────────────────────────────────────────


def _parse_delay(value: str) -> int:
    """'10m' -> 600, '90s' -> 90, '2h' -> 7200. Bare numbers mean minutes."""
    text = str(value).strip().lower()
    match = re.fullmatch(r"(\d+)\s*(s|sec|m|min|h|hr)?", text)
    if not match:
        return 600
    amount = int(match.group(1))
    unit = match.group(2) or "m"
    return amount * {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600}[unit]


def cmd_connect(args) -> int:
    from . import publish

    if not publish.configured():
        print("LinkedIn app credentials are missing.")
        print("Developer Portal -> your app -> Auth tab -> Client ID / Client Secret\n")
        client_id = input("Client ID (visible): ").strip()
        if not client_id:
            print("Cancelled.", file=sys.stderr)
            return 1
        import getpass

        secret = getpass.getpass("Client Secret (hidden, won't echo): ").strip()
        if not secret:
            print("Cancelled.", file=sys.stderr)
            return 1
        config.set_value("LINKEDIN_CLIENT_ID", client_id)
        config.set_value("LINKEDIN_CLIENT_SECRET", secret)
        print("Saved to .env\n")

    try:
        info = publish.connect(manual=getattr(args, "manual", False))
    except publish.APIError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    print(f"\nConnected as {info['name'] or 'you'}")
    print(f"  person : {info['urn']}")
    print(f"  scope  : {info['scope']}")
    print("  token  : data/auth.json (mode 600)")
    print("  revoke : https://www.linkedin.com/psettings/permitted-services")
    return 0


def cmd_whoami(_args) -> int:
    from . import publish

    info = publish.whoami()
    auth = publish.load_auth()
    note = auth.get("expires_note")
    print(f"Name     : {info.get('name', '?')}")
    print(f"Person   : {publish.person_urn()}")
    print(f"Valid    : verified just now")
    print(f"Expires  : {time.strftime('%Y-%m-%d', time.localtime(auth.get('expires_at', 0)))}"
          + (f"  ({note})" if note else ""))
    print(f"Used 24h : {publish.daily_count()}/{publish.DAILY_CAP}")
    return 0


def cmd_disconnect(_args) -> int:
    from . import publish

    publish.forget()
    print("Local token removed. Also revoke it on LinkedIn: https://www.linkedin.com/psettings/permitted-services")
    return 0


def cmd_web(args) -> int:
    from . import web

    web.serve(port=args.port, open_browser=not args.no_open, host=args.host)
    return 0


def cmd_publish(args) -> int:
    from . import publish

    if args.id:
        rec = store.find(args.id)
        text = rec["text"]
        label = rec["id"]
        check = rec
    else:
        text = _read(args.file or args.text)
        label = "inline"
        check = {"id": "inline", "kind": "post", "text": text}

    findings = safety.audit(check)
    blockers = [msg for level, msg in findings if level == safety.HIGH]
    if blockers and not args.force:
        print("Refusing to publish. Fix these first:", file=sys.stderr)
        for msg in blockers:
            print(f"  - {msg}", file=sys.stderr)
        print("  (override with --force)", file=sys.stderr)
        return 1

    visibility = "CONNECTIONS" if args.connections else "PUBLIC"

    image_path = args.image
    alt_text = args.alt
    if args.id:
        stored = (rec.get("image") or {})
        image_path = image_path or stored.get("path", "")
        alt_text = alt_text or stored.get("alt", "")
        if args.image:
            store.set_image(rec["id"], args.image, alt_text)

    if image_path and not alt_text:
        print('Tip: --alt "what the image shows" helps screen readers.', file=sys.stderr)

    if args.dry_run:
        out = publish.publish_post(
            text, visibility, dry_run=True, image_path=image_path, alt_text=alt_text
        )
        print(json.dumps(out["body"], indent=2))
        return 0

    if not args.yes:
        print(text)
        print()
        answer = input('Type "publish" to post this: ').strip().lower()
        if answer != "publish":
            print("Cancelled. Nothing was posted.")
            return 1

    result = publish.publish_post(
        text, visibility, image_path=image_path, alt_text=alt_text
    )
    if image_path:
        print(f"Image: {image_path}")
    print(f"Published: {result['url'] or result['id']}")
    if args.id:
        store.set_status(args.id, "posted")
        print(f"Marked {label} as posted.")
    return 0


def cmd_queue(args) -> int:
    from . import queue as q

    if args.cancel:
        ok = q.cancel(args.cancel)
        print(f"Cancelled {args.cancel}." if ok else f"No pending item {args.cancel}.")
        return 0 if ok else 1

    if args.approve:
        item = q.approve(args.approve)
        if not item:
            print(f"No item awaiting approval: {args.approve}")
            return 1
        when = time.strftime("%H:%M:%S", time.localtime(item["due"]))
        print(f"Approved {item['id']} — will send at {when} (lk queue --loop keeps it moving).")
        return 0

    if args.reject:
        ok = q.reject(args.reject)
        print(f"Rejected {args.reject}." if ok else f"No item awaiting approval: {args.reject}")
        return 0 if ok else 1

    if args.run or args.loop:
        sent, failed = q.run(dry_run=args.dry_run, loop=args.loop)
        print(f"{sent} sent, {failed} failed")
        return 0 if failed == 0 else 1

    items = q.listing("all")
    if not items:
        print("Queue is empty.")
        return 0
    for item in items:
        when = time.strftime("%H:%M", time.localtime(item.get("due", 0)))
        print(f"{item['id']}  {item['status']:<16} due {when}  {item['kind']:<7} {item.get('label', '')[:50]}")
    waiting = q.listing("pending-approval")
    pending = q.listing("pending")
    if waiting:
        print(f"\n{len(waiting)} awaiting your approval:  lk queue --approve <id>   or   lk queue --reject <id>")
    if pending:
        print(f"\n{len(pending)} approved. Send when due: lk queue --run   (or keep it open: lk queue --loop)")
    return 0


def cmd_inbox(args) -> int:
    from . import watch as watch_mod

    watch_mod.watch(post_urn=args.post, poll=args.poll, once=args.once)
    return 0


def cmd_profile(args) -> int:
    from . import profile as profile_mod

    result = profile_mod.update(
        cert=args.cert,
        issuer=args.issuer,
        skills=args.skills,
        achievement=args.achievement,
        role=args.role,
    )
    print()
    print(profile_mod.render(result))
    for warning in profile_mod.warnings(result):
        print(f"  ! {warning}")
    if not args.no_save:
        record = store.save("profile", args.cert or "profile update", profile_mod.render(result), result)
        print(f"\n  saved: drafts/{record['id']}.txt")
    return 0


def cmd_check(args) -> int:
    from . import feeds, publish, queue

    problems = 0
    print("lk check\n")

    # 1. Model runtime
    info = llm.health()
    if info["server"] == "up" and info["model_ready"]:
        print(f"  Ollama      OK    {info['url']}  ·  {info['model']} installed")
    elif info["server"] == "up":
        print(f"  Ollama      WARN  {info['model']} is not installed")
        print(f"                    fix: ollama pull {info['model']}")
        problems += 1
    else:
        print(f"  Ollama      FAIL  not reachable at {info['url']}")
        print("                    fix: ollama serve")
        problems += 1

    if getattr(args, "live", False) and info["server"] == "up" and info["model_ready"]:
        print("  Model load  ...   loading (this takes 10-60s)")
        good, detail = llm.live_check()
        print(f"  Model load  {'OK  ' if good else 'FAIL'}  {detail}")
        if not good:
            problems += 1

    # 2. LinkedIn token
    auth = publish.load_auth()
    if not auth.get("access_token"):
        print("  LinkedIn    WARN  no token — run: lk connect --manual")
    else:
        try:
            who = publish.whoami()
            auth = publish.load_auth()
            expiry = time.strftime("%Y-%m-%d", time.localtime(auth.get("expires_at", 0)))
            print(
                f"  LinkedIn    OK    {who.get('name', '?')}  ·  token to {expiry}"
                f"  ·  {publish.daily_count()}/{publish.DAILY_CAP} used today"
            )
        except publish.APIError as exc:
            print(f"  LinkedIn    FAIL  {exc}")
            problems += 1

    # 3. Content and local state
    drafts = store.all_drafts()
    counts = {}
    for rec in drafts:
        counts[rec["status"]] = counts.get(rec["status"], 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "none"
    print(f"  Drafts      OK    {len(drafts)} ({summary})")

    examples = voice.examples(limit=10_000)
    bad = voice.avoid(limit=10_000)
    if examples:
        print(f"  Voice       OK    {len(examples)} examples, {len(bad)} anti-examples")
    else:
        print("  Voice       WARN  0 examples — output will sound generic")
        print("                    fix: lk learn --file your_post.txt  (×5), then lk style")

    print(f"  Feeds       OK    {len(feeds.load_feeds())} configured")
    awaiting = len(queue.listing("pending-approval"))
    approved = len(queue.listing("pending"))
    print(f"  Queue       OK    {approved} approved, {awaiting} awaiting approval")

    briefs = len(list((config.DATA / "briefs").glob("*.json"))) if (config.DATA / "briefs").exists() else 0
    print(f"  Briefs      OK    {briefs} saved")

    print()
    if problems:
        print(f"{problems} problem(s) need attention.")
    else:
        print("Everything needed for a real post is working.")
    if not getattr(args, "live", False) and info["server"] == "up":
        print("Tip: `lk check --live` also loads the model to prove it runs.")
    return 1 if problems else 0


def cmd_model(args) -> int:
    info = llm.health()
    installed = info.get("installed", [])

    if not args.name:
        print(f"Current   : {config.MODEL}")
        if not installed:
            print("Installed : none — is Ollama running? (`lk doctor`)")
            return 1
        print("Installed :")
        for name in installed:
            mark = "*" if name == config.MODEL else " "
            print(f"  {mark} {name}")
        print("\nSwitch : lk model <name>")
        print("Get one: ollama pull <name>")
        return 0

    wanted = args.name.strip()
    exact = next((n for n in installed if n == wanted), None)
    if not exact:
        exact = next((n for n in installed if n.split(":")[0] == wanted), None)
    if not exact:
        print(f"'{wanted}' is not installed.", file=sys.stderr)
        print(f"  Get it first:  ollama pull {wanted}", file=sys.stderr)
        print("  See options:   lk model", file=sys.stderr)
        return 1

    config.set_value("LK_MODEL", exact)
    print(f"Model set to {exact}")
    print("Test it: lk doctor --live")
    return 0


def cmd_doctor(args) -> int:
    info = llm.health()
    print(f"Ollama URL : {info['url']}")
    print(f"Model      : {info['model']}")
    print(f"Mock mode  : {'ON' if info['mock'] else 'off'}")
    print(f"Server     : {info['server']}")
    if info["server"] == "up":
        print(f"Installed  : {', '.join(info['installed']) or 'none'}")
        print(f"Model ready: {'yes' if info['model_ready'] else 'NO — run: ollama pull ' + info['model']}")
    else:
        print("Fix        : curl -fsSL https://ollama.com/install.sh | sh")
        print(f"             ollama pull {info['model']}")
        print("Or try     : LK_MOCK=1 lk post \"test topic\"")
        return 1
    if getattr(args, "live", False) and info["server"] == "up" and not info["mock"]:
        print("Live test  : loading the model…")
        ok, detail = llm.live_check()
        print(f"Live test  : {'OK — ' + detail if ok else 'FAILED'}")
        if not ok:
            print(f"  {detail}")
            return 1
    else:
        print("Note       : this checks the model is installed, not that it runs.")
        print("             Use `lk doctor --live` for a real generation test.")
    print(f"Examples   : {len(voice.examples(limit=10_000))} saved")
    return 0


def cmd_cert(args) -> int:
    context = ""
    if args.search:
        query = args.search if args.search is not True else f"{args.title} certification skills"
        results = search.web(query)
        context = search.as_context(results)
        if context:
            args.story = (args.story + "\n" if args.story else "") + "Web context:\n" + context

    post = posts.certificate(
        title=args.title,
        issuer=args.issuer,
        skills=args.skills,
        story=args.story or "",
        tone=args.tone,
    )
    text = posts.render(post)
    record = _save("cert", args.title, text, post, args.no_save)
    _emit(f"Certificate post — {args.title}", text, posts.warnings(post), record, post if args.json else None)
    return 0


def cmd_post(args) -> int:
    context = ""
    if args.brief:
        b = brief_mod.load(args.brief)
        context = brief_mod.as_context(b)
        print(f"Using brief: {b['query']} ({len(b.get('facts', []))} facts)", file=sys.stderr)

    if args.search:
        query = args.search if args.search is not True else args.topic
        results = search.web(query)
        web_context = search.as_context(results)
        if results:
            print(f"Looked up {len(results)} sources for context.", file=sys.stderr)
        else:
            print("Search returned nothing; writing from the prompt only.", file=sys.stderr)
        context = "\n\n".join(p for p in (context, web_context) if p)

    post = posts.topic(args.topic, angle=args.angle, context=context)
    text = posts.render(post)
    record = _save("post", args.topic, text, post, args.no_save)
    _emit(f"Post — {args.topic}", text, posts.warnings(post), record, post if args.json else None)
    return 0


def cmd_reply(args) -> int:
    post_text = _read(args.post)
    result = comments.reply_to_comment(post_text, _read(args.comment), args.author)
    text = comments.render(result)
    record = _save("reply", (args.author or "reply") + ": " + result["reply"][:40], text, result, args.no_save)
    _emit("Comment reply", text, comments.warnings(result), record, result if args.json else None)

    if args.post_url:
        from . import publish
        from . import queue as q
        from . import replied

        if args.send:
            if args.author and replied.has_replied(args.post_url, args.author):
                print(
                    f"\n  skipped: already replied to {args.author} on this post "
                    "(one reply per person per post).",
                    file=sys.stderr,
                )
                return 0
            try:
                sent = publish.publish_comment(args.post_url, result["reply"])
            except publish.APIError as exc:
                print(f"\n  publish failed: {exc}", file=sys.stderr)
                return 1
            if args.author:
                replied.mark(args.post_url, args.author, note="sent immediately")
            print(f"\n  posted as comment {sent.get('id', '')}")
        else:
            try:
                item = q.add(
                    "comment",
                    args.post_url,
                    result["reply"],
                    spacing=_parse_delay(args.delay),
                    label=result["reply"][:60],
                    draft_id=record["id"] if record else "",
                    post_urn=args.post_url,
                    author=args.author,
                )
            except ValueError as exc:
                print(f"\n  skipped: {exc}", file=sys.stderr)
                return 0
            when = time.strftime("%H:%M:%S", time.localtime(item["due"]))
            print(f"\n  queued {item['id']} for {when}  (status: {item['status']})")
            if item["status"] == "pending-approval":
                print(f"  approve it: lk queue --approve {item['id']}")
    return 0


def cmd_comment(args) -> int:
    post_text = _read(args.post)
    result = comments.comment_on_post(post_text, args.angle)
    text = comments.render(result)
    record = _save("comment", result["reply"][:40], text, result, args.no_save)
    _emit("Comment on a post", text, comments.warnings(result), record, result if args.json else None)
    return 0


def cmd_search(args) -> int:
    results = search.web(args.query, limit=args.limit)
    if not results:
        print("No results (search may be rate-limited or offline).", file=sys.stderr)
        return 1
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n")
    return 0


def cmd_learn(args) -> int:
    from . import learn as learn_mod

    if args.csv:
        count = learn_mod.import_linkedin_csv(args.csv, bad=args.bad)
        print(f"Imported {count} post(s) from {args.csv}.")
    elif args.dir:
        names = learn_mod.import_dir(args.dir, note=args.note, bad=args.bad)
        print(f"Imported {len(names)} file(s): {', '.join(names[:8])}")
    else:
        text = _read(args.file) if args.file else args.text
        if not text:
            print("Give me a post with --file PATH, --text \"...\", --dir FOLDER, or --csv export.csv.", file=sys.stderr)
            return 1
        count = learn_mod.add_example(text, args.note, bad=args.bad)
        print(f"Saved as a {'negative ' if args.bad else ''}example. {count} saved total.")

    print("Run `lk style` to rewrite your style rules from everything saved.")
    return 0


def cmd_edit(args) -> int:
    """Record what you actually posted, and learn from your own edit."""
    import os
    import shlex
    import subprocess
    import tempfile

    from . import learn as learn_mod

    rec = store.find(args.id)

    if args.file or args.text:
        text = _read(args.file) if args.file else args.text
    else:
        editor = shlex.split(os.environ.get("EDITOR", "nano"))
        tmp = Path(tempfile.mkdtemp(prefix="lk-", dir="/tmp/opencode")) / "draft.txt"
        tmp.write_text(rec["text"])
        subprocess.run([*editor, str(tmp)])
        text = tmp.read_text()

    if not text.strip():
        print("Empty text; nothing changed.", file=sys.stderr)
        return 1

    updated = store.update_text(args.id, text)
    print(f"Updated {updated['id']} ({updated['chars']} chars).")
    if not args.no_learn:
        total = learn_mod.add_example(updated["text"], note=f"final version of {updated['id']}")
        print(f"Learned your edit as example #{total}.")
    return 0


def cmd_style(_args) -> int:
    from . import learn as learn_mod

    rules = learn_mod.analyze()
    print(rules)
    print(
        f"\nWritten to data/style.md "
        f"({len(voice.examples(limit=10_000))} examples, {len(voice.avoid(limit=10_000))} anti-examples)."
    )
    return 0


def cmd_list(args) -> int:
    rows = store.all_drafts(status=args.status)
    if not rows:
        print("No drafts yet.")
        return 0
    for r in rows:
        print(f"{r['id']}  [{r['kind']:<7}] [{r['status']:<6}] {r['chars']:>4}c  {r['title'][:50]}")
    return 0


def cmd_show(args) -> int:
    rec = store.find(args.id)
    print(rec["text"])
    print(f"\n({rec['chars']} characters, status={rec['status']}, created={rec['created']})")
    return 0


def cmd_copy(args) -> int:
    rec = store.find(args.id)
    try:
        import subprocess

        subprocess.run(["xclip", "-selection", "clipboard"], input=rec["text"].encode(), check=True)
        print(f"Copied {rec['id']} to clipboard.")
    except Exception:  # noqa: BLE001
        print(rec["text"])
    return 0


def cmd_watch(args) -> int:
    from . import feeds

    if args.add:
        label = feeds.add_feed(args.add, args.name)
        print(f"Added '{label}'. {len(feeds.load_feeds())} feeds total.")
        return 0
    if args.remove:
        ok = feeds.remove_feed(args.remove)
        print(f"Removed '{args.remove}'." if ok else f"No feed matching '{args.remove}'.")
        return 0 if ok else 1

    rows = feeds.load_feeds()
    print(f"{len(rows)} feeds:")
    for name, url in rows.items():
        print(f"  {name:<22} {url}")
    if not args.list:
        print("\nAdd one: lk watch --add https://example.com/feed/ --name Example")
    return 0


def cmd_humanize(args) -> int:
    from . import humanize as hz

    if args.id:
        rec = store.find(args.id)
    else:
        rows = store.all_drafts()
        if not rows:
            print("No drafts yet.", file=sys.stderr)
            return 1
        rec = rows[0]

    original = rec.get("text", "")
    cleaned, changes = hz.humanize(original)
    openers = hz.repeated_openers(cleaned)
    hype = hz.hype_words(cleaned)

    print(f"\n── Humanize {rec['id']} " + "─" * max(0, 50 - len(rec["id"])))
    print()
    print(hz.report(original, changes))
    if hype:
        print("  ! hype words to rewrite yourself: " + ", ".join(hype))
    if openers:
        print("  ! repeated line openers: " + ", ".join(openers))
    print()

    if args.dry_run:
        print("--- result (not saved) ---")
        print(cleaned)
        return 0

    if not changes:
        print("Already clean. Nothing saved.")
        return 0

    store.update_text(rec["id"], cleaned)
    print(f"  saved: {rec['id']}  ({len(changes)} change(s))")
    return 0


def cmd_hooks(args) -> int:
    from . import hooks as hooks_mod

    if not args.apply:
        print()
        print(hooks_mod.render())
        print()
        print("Use one: lk hooks --apply <draft-id> --formula \"open loop\"")
        return 0

    rec = store.find(args.apply)
    result = hooks_mod.rewrite_hook(rec.get("text", ""), args.formula)
    print()
    print(f"── Hook: {result['formula']} " + "─" * 30)
    print()
    print(f"old: {result['old']}")
    print(f"new: {result['new']}")
    print()
    if args.dry_run:
        print("--- full text (not saved) ---")
        print(result["text"])
        return 0
    store.update_text(rec["id"], result["text"])
    print(f"  saved: {rec['id']}")
    return 0


def cmd_plan(args) -> int:
    from . import plan as plan_mod

    text = plan_mod.build(posts_per_week=args.posts)
    print()
    print(text)
    if not args.no_save:
        rec = plan_mod.save(text)
        print()
        print(f"  saved: {rec['id']}")
    return 0


def cmd_digest(args) -> int:
    from . import feeds
    digest = feeds.collect(hours=args.hours, top=args.top, include_seen=args.all)
    if digest["count"] == 0:
        print(f"No new items in the last {args.hours}h.")
        if digest["failures"]:
            print(f"Unreachable feeds: {', '.join(digest['failures'])}")
        return 0

    text = feeds.render(digest)
    print(text)
    if not args.no_save:
        path = feeds.save(digest, text)
        print(f"Saved: {path}")
    return 0


def cmd_coach(args) -> int:
    if args.id:
        text = store.find(args.id)["text"]
    else:
        text = _read(args.file or args.text)
    if not text.strip():
        print("Give me a post: lk coach <id>, --file PATH, or --text \"...\"", file=sys.stderr)
        return 1

    result = coach.analyze(text)
    print(coach.render(result, show_rewrite=args.rewrite))
    if args.json:
        print()
        print(coach.to_json(result))
    if args.learn:
        from . import learn as learn_mod

        total = learn_mod.add_example(text, note="reviewed with lk coach")
        print(f"\nLearned as voice example #{total}.")
    return 0


def cmd_brief(args) -> int:
    if args.show is not None:
        b = brief_mod.load(args.show)
        print(brief_mod.render(b))
        return 0

    if args.url:
        print(f"Reading: {args.url}", file=sys.stderr)
        b = brief_mod.build_url(args.url, args.query)
        path = brief_mod.save(b)
        print(brief_mod.render(b))
        print(f"\nSaved: {path}")
        print(f'Write the post with: lk post "{b["query"][:40]}" --brief {path.stem}')
        return 0

    if not args.query:
        print("Give me a topic: lk brief \"zero trust for small teams\"  (or --url LINK)", file=sys.stderr)
        return 1

    print(f"Reading the top {args.pages} pages about: {args.query}", file=sys.stderr)
    b = brief_mod.build(args.query, pages=args.pages)
    path = brief_mod.save(b)
    print(brief_mod.render(b))
    print(f"\nSaved: {path}")
    print(f'Write the post with: lk post "{args.query}" --brief {path.stem}')
    return 0


def cmd_ref(args) -> int:
    """Other people's posts: structure reference only."""
    from . import learn as learn_mod

    if args.analyze:
        rules = learn_mod.analyze_reference()
        print(rules)
        print(f"\nWritten to data/reference.md ({len(voice.refs(limit=10_000))} reference posts).")
        return 0

    if args.list:
        rows = voice.refs(limit=10_000)
        if not rows:
            print("No reference posts yet.")
            return 0
        for i, row in enumerate(rows, 1):
            first = row["text"].splitlines()[0][:70]
            print(f"{i:>2}. {first}")
        return 0

    if args.dir:
        names = learn_mod.import_dir(args.dir, note=args.note, ref=True)
        print(f"Imported {len(names)} reference post(s): {', '.join(names[:8])}")
    elif args.file or args.text:
        text = _read(args.file) if args.file else args.text
        count = learn_mod.add_reference(text, args.note)
        print(f"Saved reference post. {count} saved total.")
    else:
        print("Use --file, --text, --dir, --list or --analyze.", file=sys.stderr)
        return 1

    print("Run `lk ref --analyze` to distil structural patterns. Voice is unaffected.")
    return 0


def cmd_safe(args) -> int:
    if args.id:
        rec = store.find(args.id)
    else:
        rows = store.all_drafts()
        if not rows:
            print("No drafts to check.")
            return 0
        rec = rows[0]
    print(f"Draft {rec['id']}  [{rec['kind']}] {len(rec['text'])} chars")
    ok = safety.report(rec, header="Result")
    print(f"  verdict: {'safe to paste' if ok else 'fix the HIGH items first'}")
    return 0 if ok else 1


def cmd_mark(args) -> int:
    rec = store.set_status(args.id, args.status)
    print(f"{rec['id']} → {rec['status']}")
    return 0


def learn_add(text: str, note: str) -> int:
    from . import learn as learn_mod

    return learn_mod.add_example(text, note or "")
# ── parser ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lk",
        description="Local LinkedIn writing agent. Drafts only — nothing is posted automatically.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="check Ollama and model status")
    d.add_argument("--live", action="store_true", help="load the model with a one-token request")
    d.set_defaults(func=cmd_doctor)

    md = sub.add_parser("model", help="show or switch the local model")
    md.add_argument("name", nargs="?", default="", help="model to switch to, e.g. qwen2.5-coder:7b")
    md.set_defaults(func=cmd_model)

    ck = sub.add_parser("check", help="check every subsystem in one pass")
    ck.add_argument("--live", action="store_true", help="also load the model to prove it runs")
    ck.set_defaults(func=cmd_check)

    c = sub.add_parser("cert", help="storytelling post for a certificate or badge")
    c.add_argument("--title", required=True, help="certificate name")
    c.add_argument("--issuer", default="", help="who issued it")
    c.add_argument("--skills", default="", help="skills covered, comma separated")
    c.add_argument("--story", default="", help="what actually happened (file path or text)")
    c.add_argument("--tone", default="", help="e.g. honest, funny, no emoji")
    c.add_argument("--search", nargs="?", const=True, default=None, help="look up context first")
    c.add_argument("--json", action="store_true", help="also print the raw JSON")
    c.add_argument("--no-save", action="store_true")
    c.set_defaults(func=cmd_cert)

    po = sub.add_parser("post", help="write a post about any topic")
    po.add_argument("topic")
    po.add_argument("--angle", default="", help="the take you want to make")
    po.add_argument("--search", nargs="?", const=True, default=None, help="research the topic first")
    po.add_argument("--brief", default="", help="use a saved brief ('latest' or its id)")
    po.add_argument("--json", action="store_true")
    po.add_argument("--no-save", action="store_true")
    po.set_defaults(func=cmd_post)

    r = sub.add_parser("reply", help="draft a reply to a comment on your post")
    r.add_argument("--post", required=True, help="path to your post, '-' for stdin, or text")
    r.add_argument("--comment", required=True, help="path, '-' for stdin, or the comment text")
    r.add_argument("--author", default="", help="commenter's name")
    r.add_argument("--post-url", default="", help="LinkedIn post or comment URL to reply under")
    r.add_argument("--send", action="store_true", help="post the reply now instead of queueing it")
    r.add_argument("--delay", default="5m", help="spacing before this reply goes out (default 5m)")
    r.add_argument("--json", action="store_true")
    r.add_argument("--no-save", action="store_true")
    r.set_defaults(func=cmd_reply)

    cm = sub.add_parser("comment", help="draft a comment on someone else's post")
    cm.add_argument("--post", required=True, help="path, '-' for stdin, or text")
    cm.add_argument("--angle", default="", help="what you want to add")
    cm.add_argument("--json", action="store_true")
    cm.add_argument("--no-save", action="store_true")
    cm.set_defaults(func=cmd_comment)

    s = sub.add_parser("search", help="look something up on the web")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(func=cmd_search)

    l = sub.add_parser("learn", help="teach the agent from your own posts")
    l.add_argument("--file", default="", help="path to the post (or '-' for stdin)")
    l.add_argument("--text", default="", help="post text inline")
    l.add_argument("--dir", default="", help="import every .txt/.md file in a folder")
    l.add_argument("--csv", default="", help="import Posts.csv from your LinkedIn data export")
    l.add_argument("--note", default="", help="what you like (or dislike) about it")
    l.add_argument("--bad", action="store_true", help="save as an anti-example: never write like this")
    l.set_defaults(func=cmd_learn)

    e = sub.add_parser("edit", help="record what you actually posted, and learn from your edit")
    e.add_argument("id")
    e.add_argument("--file", default="", help="final text from a file")
    e.add_argument("--text", default="", help="final text inline")
    e.add_argument("--no-learn", action="store_true", help="update the draft but do not treat it as an example")
    e.set_defaults(func=cmd_edit)

    st = sub.add_parser("style", help="rewrite style rules from saved examples")
    st.set_defaults(func=cmd_style)

    ls = sub.add_parser("list", help="list drafts")
    ls.add_argument("--status", default=None, choices=["draft", "posted", "rejected"])
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="print a draft")
    sh.add_argument("id")
    sh.set_defaults(func=cmd_show)

    cp = sub.add_parser("copy", help="copy a draft to the clipboard")
    cp.add_argument("id")
    cp.set_defaults(func=cmd_copy)

    mk = sub.add_parser("mark", help="change a draft's status")
    mk.add_argument("id")
    mk.add_argument("--status", default="posted", choices=["draft", "posted", "rejected"])
    mk.set_defaults(func=cmd_mark)

    cn = sub.add_parser("connect", help="authorise the LinkedIn API (OAuth, no cookies)")
    cn.add_argument("--manual", action="store_true", help="print the URL and paste the code back (use in WSL)")
    cn.set_defaults(func=cmd_connect)

    wh = sub.add_parser("whoami", help="show the connected account and daily usage")
    wh.set_defaults(func=cmd_whoami)

    dc = sub.add_parser("disconnect", help="delete the local token")
    dc.set_defaults(func=cmd_disconnect)

    pb = sub.add_parser("publish", help="post a draft to LinkedIn through the official API")
    pb.add_argument("id", nargs="?", default="", help="draft id")
    pb.add_argument("--file", default="", help="post text from a file")
    pb.add_argument("--text", default="", help="post text inline")
    pb.add_argument("--connections", action="store_true", help="visible to connections only")
    pb.add_argument("--dry-run", action="store_true", help="show the request body, post nothing")
    pb.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    pb.add_argument("--force", action="store_true", help="publish even if the safety check flags it")
    pb.add_argument("--image", default="", help="JPG/PNG/GIF to attach to the post")
    pb.add_argument("--alt", default="", help="alt text for the image (accessibility)")
    pb.set_defaults(func=cmd_publish)

    qq = sub.add_parser("queue", help="scheduled replies, spaced apart")
    qq.add_argument("--list", action="store_true", help="show the queue (default)")
    qq.add_argument("--run", action="store_true", help="send everything that is due")
    qq.add_argument("--loop", action="store_true", help="keep running and send items as they come due")
    qq.add_argument("--dry-run", action="store_true")
    qq.add_argument("--cancel", default="", help="cancel a pending item")
    qq.add_argument("--approve", default="", help="approve a drafted reply so it may send")
    qq.add_argument("--reject", default="", help="reject a drafted reply (never sends)")
    qq.set_defaults(func=cmd_queue)

    wt = sub.add_parser("inbox", help="watch your posts for new comments and draft replies")
    wt.add_argument("--post", default="", help="watch one post URL/URN (default: your recent posts)")
    wt.add_argument("--poll", type=int, default=0, help="seconds between checks (default 900)")
    wt.add_argument("--once", action="store_true", help="check once and exit")
    wt.set_defaults(func=cmd_inbox)

    pf = sub.add_parser("profile", help="write new headline and About after an achievement (you paste)")
    pf.add_argument("--cert", default="", help="certificate or badge name")
    pf.add_argument("--issuer", default="")
    pf.add_argument("--skills", default="")
    pf.add_argument("--achievement", default="", help="what actually happened")
    pf.add_argument("--role", default="")
    pf.add_argument("--no-save", action="store_true")
    pf.set_defaults(func=cmd_profile)

    sf = sub.add_parser("safe", help="check a draft for spam and ban signals")
    sf.add_argument("id", nargs="?", default="", help="draft id (default: newest)")
    sf.set_defaults(func=cmd_safe)

    rf = sub.add_parser("ref", help="save someone else's post as a structure reference (never as your voice)")
    rf.add_argument("--file", default="", help="path to a text file")
    rf.add_argument("--text", default="", help="post text inline")
    rf.add_argument("--dir", default="", help="import every .txt/.md in a folder")
    rf.add_argument("--note", default="", help="why it worked")
    rf.add_argument("--analyze", action="store_true", help="distil structural patterns into data/reference.md")
    rf.add_argument("--list", action="store_true", help="list saved reference posts")
    rf.set_defaults(func=cmd_ref)

    br = sub.add_parser("brief", help="research a topic on the public web into a post brief")
    br.add_argument("query", nargs="?", default="")
    br.add_argument("--pages", type=int, default=3, help="how many pages to read (default 3)")
    br.add_argument("--url", default="", help="brief one specific article")
    br.add_argument("--show", nargs="?", const="latest", default=None, help="print a saved brief")
    br.set_defaults(func=cmd_brief)

    w = sub.add_parser("watch", help="manage RSS/Atom feeds for the research digest")
    w.add_argument("--list", action="store_true")
    w.add_argument("--add", default="", help="feed URL")
    w.add_argument("--name", default="", help="short label for the feed")
    w.add_argument("--remove", default="", help="feed label")
    w.set_defaults(func=cmd_watch)

    hu = sub.add_parser("humanize", help="strip em dashes, invisible chars and filler words")
    hu.add_argument("id", nargs="?", default="", help="draft id (default: newest)")
    hu.add_argument("--dry-run", action="store_true", help="show the result without saving")
    hu.set_defaults(func=cmd_humanize)

    hk = sub.add_parser("hooks", help="21 opening-line formulas, and rewrite a draft's hook")
    hk.add_argument("--apply", default="", help="draft id to rewrite")
    hk.add_argument("--formula", default="", help="hook name (default: confession)")
    hk.add_argument("--dry-run", action="store_true", help="show the new opening without saving")
    hk.set_defaults(func=cmd_hooks)

    pl = sub.add_parser("plan", help="a week of suggestions: what to post, when, what to engage")
    pl.add_argument("--posts", type=int, default=3, help="posts per week (default 3)")
    pl.add_argument("--no-save", action="store_true")
    pl.set_defaults(func=cmd_plan)

    dg = sub.add_parser("digest", help="collect new articles from your feeds")
    dg.add_argument("--hours", type=int, default=48, help="look back this many hours (default 48)")
    dg.add_argument("--top", type=int, default=4, help="max items per feed (default 4)")
    dg.add_argument("--all", action="store_true", help="include items already shown before")
    dg.add_argument("--no-save", action="store_true")
    dg.set_defaults(func=cmd_digest)

    co = sub.add_parser("coach", help="score a draft against LinkedIn storytelling beats")
    co.add_argument("id", nargs="?", default="", help="draft id")
    co.add_argument("--file", default="", help="path to a text file")
    co.add_argument("--text", default="", help="post text inline")
    co.add_argument("--rewrite", action="store_true", help="also show a rewritten version")
    co.add_argument("--json", action="store_true", help="print the raw JSON too")
    co.add_argument("--learn", action="store_true", help="save this post as a voice example")
    co.set_defaults(func=cmd_coach)

    wb = sub.add_parser("web", help="open the local web UI (drafts, coach, publish)")
    wb.add_argument("--port", type=int, default=8080, help="port to listen on (default 8080)")
    wb.add_argument("--host", default="127.0.0.1", help="bind address (use 0.0.0.0 to reach it from Windows)")
    wb.add_argument("--no-open", action="store_true", help="do not open a browser automatically")
    wb.set_defaults(func=cmd_web)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    from . import publish

    try:
        return args.func(args)
    except (llm.LLMError, publish.APIError) as exc:
        print(f"\nError: {exc}\n", file=sys.stderr)
        return 2
    except (KeyError, ValueError) as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
