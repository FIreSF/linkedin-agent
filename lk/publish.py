"""Official LinkedIn API: OAuth, posting, and comment replies.

Uses only the sanctioned endpoints and the w_member_social scope. No cookies,
no session tokens, no browser. The token is revocable from LinkedIn settings.
"""

import base64
import json
import os
import re
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

from . import config

AUTH_FILE = config.DATA / "auth.json"
USAGE_FILE = config.DATA / "usage.json"
REPLIES_FILE = config.DATA / "replies.json"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
IMAGES_URL = "https://api.linkedin.com/rest/images"
SOCIAL_URL = "https://api.linkedin.com/v2/socialActions"

SCOPES = "openid profile w_member_social"
DEFAULT_PORT = 8765


class APIError(RuntimeError):
    pass


def approved_pending_only() -> bool:
    return config.get("LK_REQUIRE_APPROVAL", "1") not in ("0", "false", "no", "off")


def in_quiet_hours(now: float | None = None) -> bool:
    start = int(config.get("LK_QUIET_START", "22") or 22)
    end = int(config.get("LK_QUIET_END", "8") or 8)
    hour = int(time.strftime("%H", time.localtime(now or time.time())))
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def daily_reply_count() -> int:
    if not REPLIES_FILE.exists():
        return 0
    try:
        stamps = json.loads(REPLIES_FILE.read_text())
    except json.JSONDecodeError:
        return 0
    return len([t for t in stamps if time.time() - t < 86400])


def _record_reply() -> None:
    try:
        stamps = json.loads(REPLIES_FILE.read_text()) if REPLIES_FILE.exists() else []
    except json.JSONDecodeError:
        stamps = []
    stamps = [t for t in stamps if time.time() - t < 86400]
    stamps.append(time.time())
    REPLIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPLIES_FILE.write_text(json.dumps(stamps))


def daily_reply_cap() -> int:
    return int(config.get("LK_MAX_REPLIES_PER_DAY", "5") or 5)


def reply_spacing() -> int:
    return int(config.get("LK_REPLY_SPACING_S", "360") or 360)


# ── token storage ────────────────────────────────────────────────────────


def load_auth() -> dict:
    if not AUTH_FILE.exists():
        return {}
    try:
        return json.loads(AUTH_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save_auth(data: dict) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(AUTH_FILE, 0o600)


def forget() -> None:
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()


def configured() -> bool:
    return bool(config.get("LINKEDIN_CLIENT_ID") and config.get("LINKEDIN_CLIENT_SECRET"))


def redirect_uri() -> str:
    return config.get("LINKEDIN_REDIRECT", f"http://localhost:{DEFAULT_PORT}/callback")


def api_version() -> str:
    return config.get("LK_LINKEDIN_VERSION", "202610")


# ── OAuth ────────────────────────────────────────────────────────────────


def scopes() -> str:
    return config.get("LK_SCOPES", SCOPES)


def build_auth_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": config.get("LINKEDIN_CLIENT_ID"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": scopes(),
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _token_request(payload: dict) -> dict:
    payload = {
        **payload,
        "client_id": config.get("LINKEDIN_CLIENT_ID"),
        "client_secret": config.get("LINKEDIN_CLIENT_SECRET"),
    }
    resp = requests.post(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise APIError(f"Token request failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def exchange_code(code: str) -> dict:
    data = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
        }
    )
    return _store(data)


def refresh() -> dict:
    auth = load_auth()
    token = auth.get("refresh_token")
    if not token:
        raise APIError("No refresh token. Run `lk connect` again.")
    data = _token_request({"grant_type": "refresh_token", "refresh_token": token})
    kept = {"refresh_token": token, "person_urn": auth.get("person_urn"), "name": auth.get("name")}
    return _store(data, kept)


def _store(data: dict, kept: dict | None = None) -> dict:
    auth = load_auth()
    record = {
        "access_token": data["access_token"],
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
        "scope": data.get("scope", SCOPES),
        "refresh_token": data.get("refresh_token") or (kept or {}).get("refresh_token") or auth.get("refresh_token", ""),
        "person_urn": (kept or {}).get("person_urn") or auth.get("person_urn", ""),
        "name": (kept or {}).get("name") or auth.get("name", ""),
    }
    save_auth(record)
    return record


def access_token() -> str:
    auth = load_auth()
    if not auth.get("access_token"):
        raise APIError("Not connected. Run `lk connect` first.")
    if auth.get("expires_at", 0) - 300 > time.time():
        return auth["access_token"]
    if auth.get("refresh_token"):
        try:
            return refresh()["access_token"]
        except APIError:
            pass
    # No refresh token available: hand the token over anyway and let the API
    # decide. LinkedIn often reports a short expires_in for tokens that stay
    # valid much longer.
    return auth["access_token"]


def _fail(resp, what: str) -> None:
    if resp.status_code == 401:
        raise APIError(
            f"{what} failed: token expired or revoked.\n"
            "  Reconnect: lk connect --manual"
        )
    if resp.status_code == 403:
        raise APIError(
            f"{what} failed: not permitted ({resp.status_code}).\n"
            "  Check that 'Share on LinkedIn' is still on your app's Products tab."
        )
    if resp.status_code >= 400:
        raise APIError(f"{what} failed ({resp.status_code}): {resp.text[:300]}")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {access_token()}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": api_version(),
        "Content-Type": "application/json",
    }


def whoami() -> dict:
    resp = requests.get(USERINFO_URL, headers=_headers(), timeout=30)
    _fail(resp, "userinfo")
    data = resp.json()
    sub = data.get("sub", "")
    auth = load_auth()
    auth["last_verified"] = int(time.time())
    if sub and not auth.get("person_urn"):
        auth["person_urn"] = f"urn:li:person:{sub}"
        auth["name"] = data.get("name", "")
    # LinkedIn documents a 60-day token but sometimes reports a 1-hour TTL.
    # If the token demonstrably works, trust the documented lifetime.
    if auth.get("expires_at", 0) - time.time() < 86400:
        auth["expires_at"] = int(time.time()) + 60 * 86400
        auth["expires_note"] = "assumed 60d (LinkedIn reported a short TTL)"
    save_auth(auth)
    return data


def person_urn() -> str:
    urn = load_auth().get("person_urn", "")
    if urn:
        return urn
    whoami()
    urn = load_auth().get("person_urn", "")
    if not urn:
        raise APIError("Could not resolve your person URN. Run `lk connect` again.")
    return urn


# ── connect flow ─────────────────────────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        _Handler.result = {k: v[0] for k, v in query.items()}
        body = b"<html><body style='font-family:sans-serif;padding:40px'><h2>lk is connected.</h2><p>You can close this tab.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def _explain_error(result: dict) -> str:
    code = result.get("error", "")
    detail = result.get("error_description", "")
    if code == "unauthorized_scope_error":
        return (
            "Your app is missing a product.\n"
            "  Add 'Sign In with LinkedIn using OpenID Connect' on the Products tab;\n"
            "  that is what grants the openid and profile scopes. Share on LinkedIn\n"
            "  alone only grants w_member_social."
        )
    if code == "invalid_scope":
        return (
            "The requested scopes are not active yet.\n"
            "  Check the Products tab for 'Share on LinkedIn' and\n"
            "  'Sign In with LinkedIn using OpenID Connect', then retry in a minute."
        )
    return f"LinkedIn returned: {detail or code}"


def _parse_callback(raw: str) -> dict:
    """Accept a full redirect URL, a query string, or a bare code."""
    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("http"):
        query = parse_qs(urlparse(raw).query)
    elif "code=" in raw:
        query = parse_qs(raw)
    else:
        return {"code": raw}
    return {k: v[0] for k, v in query.items()}


def connect(timeout: int = 180, manual: bool = False) -> dict:
    """Open the browser, catch the redirect, store the token.

    If the redirect cannot reach this machine (common under WSL), paste the
    URL you landed on and the code is extracted from it.
    """
    if not configured():
        raise APIError(
            "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first.\n"
            "Create the app at https://www.linkedin.com/developers/apps and add the "
            "'Share on LinkedIn' product."
        )
    state = secrets.token_urlsafe(16)
    url = build_auth_url(state)

    if manual:
        print("Open this URL and approve access:\n")
        print(url)
        print()
        raw = input("Paste the full URL you were redirected to (or just the code): ")
        result = _parse_callback(raw)
    else:
        port = urlparse(redirect_uri()).port or DEFAULT_PORT
        server = HTTPServer(("127.0.0.1", port), _Handler)
        server.timeout = timeout
        _Handler.result = {}

        print("Opening your browser to approve access...")
        print(f"If it does not open, visit:\n{url}\n")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

        try:
            server.handle_request()
        finally:
            server.server_close()

        result = dict(_Handler.result)
        if not result.get("code"):
            print("\nThe redirect did not reach this machine — normal inside WSL.")
            print("Copy the URL from your browser's address bar (it contains ?code=...).")
            raw = input("Paste it here: ")
            result = _parse_callback(raw)

    if result.get("error"):
        raise APIError(_explain_error(result))
    if not result.get("code"):
        raise APIError("No authorization code received. Try `lk connect` again.")
    if result.get("state") and result["state"] != state:
        raise APIError("State mismatch; refusing the token. Run `lk connect` again.")

    _store(exchange_code(result["code"]))
    info = whoami()
    return {"name": info.get("name", ""), "urn": person_urn(), "scope": load_auth().get("scope", "")}


# ── usage guard ──────────────────────────────────────────────────────────


def _usage() -> list[float]:
    if not USAGE_FILE.exists():
        return []
    try:
        return [float(t) for t in json.loads(USAGE_FILE.read_text())]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _record_use() -> None:
    now = time.time()
    stamps = [t for t in _usage() if now - t < 86400] + [now]
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(stamps))


def daily_count() -> int:
    now = time.time()
    return len([t for t in _usage() if now - t < 86400])


DAILY_CAP = 120  # LinkedIn allows 150; stay well under


# ── publish ──────────────────────────────────────────────────────────────


IMAGE_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def validate_image(path: str) -> str:
    """Check an image before any network call. Returns the extension."""
    from pathlib import Path

    file = Path(path).expanduser()
    if not file.exists():
        raise APIError(f"Image not found: {file}")
    if not file.is_file():
        raise APIError(f"Not a file: {file}")
    ext = file.suffix.lower().lstrip(".")
    if ext not in IMAGE_TYPES:
        raise APIError("Image must be JPG, PNG or GIF.")
    size = file.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise APIError(f"Image is {size / 1_048_576:.1f} MB; keep it under 10 MB.")
    if size == 0:
        raise APIError("Image file is empty.")
    return ext


def upload_image(path: str, alt_text: str = "") -> str:
    """Upload a local image and return its urn:li:image:... id.

    Two steps, both official: initializeUpload, then PUT the bytes to the
    returned URL. No cookies, no browser.
    """
    from pathlib import Path

    ext = validate_image(path)
    file = Path(path).expanduser()

    init = requests.post(
        f"{IMAGES_URL}?action=initializeUpload",
        headers=_headers(),
        json={"initializeUploadRequest": {"owner": person_urn()}},
        timeout=30,
    )
    _fail(init, "Image upload setup")
    if init.status_code not in (200, 201):
        raise APIError(f"Image upload setup failed ({init.status_code}): {init.text[:300]}")

    value = init.json().get("value") or {}
    upload_url = value.get("uploadUrl")
    image_urn = value.get("image")
    if not (upload_url and image_urn):
        raise APIError("LinkedIn did not return an upload URL. Try again.")

    with file.open("rb") as fh:
        put = requests.put(
            upload_url,
            data=fh,
            headers={
                "Authorization": f"Bearer {access_token()}",
                "Content-Type": IMAGE_TYPES[ext],
            },
            timeout=120,
        )
    if put.status_code not in (200, 201):
        raise APIError(f"Image upload failed ({put.status_code}): {put.text[:300]}")
    return image_urn


def publish_post(
    text: str,
    visibility: str = "PUBLIC",
    dry_run: bool = False,
    image_path: str = "",
    alt_text: str = "",
) -> dict:
    text = text.strip()
    if not text:
        raise APIError("Nothing to post.")
    if len(text) > 3000:
        raise APIError(f"{len(text)} characters; the limit is 3000.")
    if visibility not in ("PUBLIC", "CONNECTIONS"):
        raise APIError("visibility must be PUBLIC or CONNECTIONS")
    if image_path:
        validate_image(image_path)

    if daily_count() >= DAILY_CAP:
        raise APIError(f"Daily cap reached ({DAILY_CAP}). Try again tomorrow.")

    body = {
        "author": person_urn(),
        "commentary": text,
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if dry_run:
        if image_path:
            body["content"] = {
                "media": {
                    "id": "urn:li:image:<uploaded at publish>",
                    "altText": (alt_text or "Image shared with this post")[:300],
                }
            }
        return {"dry_run": True, "body": body, "image": image_path}

    if image_path:
        body["content"] = {
            "media": {
                "id": upload_image(image_path, alt_text),
                "altText": (alt_text or "Image shared with this post")[:300],
            }
        }

    resp = requests.post(POSTS_URL, headers=_headers(), json=body, timeout=30)
    _fail(resp, "Post")
    if resp.status_code not in (200, 201):
        raise APIError(f"Post failed ({resp.status_code}): {resp.text[:300]}")
    post_id = resp.headers.get("x-restli-id", "")
    _record_use()
    return {"id": post_id, "url": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""}


def parse_urn(url_or_urn: str) -> dict:
    """Accept a LinkedIn URL or a raw URN and return what we need to comment."""
    value = unquote(url_or_urn.strip())
    match = re.search(r"urn:li:(activity|ugcPost|share|comment):([^/?#\s]+)", value)
    if not match:
        m2 = re.search(r"(?:activity|update)[:/-](\d{15,25})", value)
        if m2:
            return {"object": f"urn:li:activity:{m2.group(1)}", "parent": ""}
        raise APIError("Could not find a post URN in that link. Use the post's own URL.")

    kind, raw = match.group(1), match.group(2)
    if kind == "comment":
        inner = raw.strip("()")
        activity = re.search(r"activity:(\d+)", inner)
        if not activity:
            raise APIError("Could not read the activity inside that comment link.")
        return {
            "object": f"urn:li:activity:{activity.group(1)}",
            "parent": f"urn:li:comment:({inner})",
        }
    return {"object": f"urn:li:{kind}:{raw}", "parent": ""}


def publish_comment(url_or_urn: str, text: str, dry_run: bool = False) -> dict:
    text = text.strip()
    if not text:
        raise APIError("Nothing to say.")
    if len(text) > 1250:
        raise APIError(f"{len(text)} characters; comment limit is 1250.")
    if daily_count() >= DAILY_CAP:
        raise APIError(f"Daily cap reached ({DAILY_CAP}). Try again tomorrow.")

    if daily_reply_count() >= daily_reply_cap():
        raise APIError(f"Daily reply cap reached ({daily_reply_cap()}). Low-activity mode.")

    if in_quiet_hours() and not dry_run:
        raise APIError("Quiet hours — reply will be queued and sent after. Try lk queue --loop during the day.")

    target = parse_urn(url_or_urn)
    body = {
        "actor": person_urn(),
        "object": target["object"],
        "message": {"text": text},
    }
    if target["parent"]:
        body["parentComment"] = target["parent"]

    if dry_run:
        return {"dry_run": True, "body": body}

    resp = requests.post(
        f"{SOCIAL_URL}/{quote(target['object'], safe='')}/comments",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    _fail(resp, "Comment")
    if resp.status_code not in (200, 201):
        raise APIError(f"Comment failed ({resp.status_code}): {resp.text[:300]}")
    _record_use()
    _record_reply()
    return {"id": resp.headers.get("x-restli-id", "")}


def insights(post_urn: str) -> dict:
    """Likes and comment counts for one of your own posts."""
    url = f"{SOCIAL_URL}/{quote(post_urn, safe='')}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    _fail(resp, "Reading that post")
    return resp.json()


# ── reading comments (needs r_member_social / partner access) ────────────


class ReadPermissionError(APIError):
    """Raised when the app may not read comments (403 / missing scope)."""


def list_comments(post_urn: str, count: int = 50) -> list[dict]:
    """Read comments on one of your posts.

    This needs a permission the posting-only scope does not have. When that is
    missing we raise ReadPermissionError with the exact message, so the caller
    can tell the user what to enable instead of guessing.
    """
    url = f"{SOCIAL_URL}/{quote(post_urn, safe='')}/comments"
    try:
        resp = requests.get(
            url,
            headers=_headers(),
            params={"count": count},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise APIError(f"Could not reach LinkedIn: {exc}") from exc

    if resp.status_code in (401, 403):
        raise ReadPermissionError(
            f"LinkedIn refused to read comments ({resp.status_code}): {resp.text[:200]}"
        )
    if resp.status_code >= 400:
        raise APIError(f"Reading comments failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    rows = data.get("elements", []) if isinstance(data, dict) else []
    out = []
    for row in rows:
        actor = row.get("actor", "") or ""
        out.append(
            {
                "id": row.get("$URN") or row.get("id", ""),
                "urn": row.get("$URN", ""),
                "author_urn": actor,
                "author": _actor_name(actor) or actor.split(":")[-1],
                "text": (row.get("message", {}) or {}).get("text", ""),
                "created": row.get("created", {}).get("time", 0)
                if isinstance(row.get("created"), dict)
                else row.get("created", 0),
            }
        )
    return out


def _actor_name(actor_urn: str) -> str:
    """Best-effort display name for a commenter URN. Never raises."""
    if not actor_urn.startswith("urn:li:person:"):
        return ""
    try:
        resp = requests.get(
            "https://api.linkedin.com/v2/people/" + quote(actor_urn.split(":")[-1], safe=""),
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code >= 400:
            return ""
        data = resp.json()
        first = (data.get("localizedFirstName") or "").strip()
        last = (data.get("localizedLastName") or "").strip()
        return " ".join(p for p in (first, last) if p)
    except requests.RequestException:
        return ""


def my_recent_posts(count: int = 10) -> list[dict]:
    """Return my own recent posts (URN + commentary), newest first."""
    url = POSTS_URL
    try:
        resp = requests.get(
            url,
            headers=_headers(),
            params={"author": person_urn(), "q": "author", "count": count},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise APIError(f"Could not reach LinkedIn: {exc}") from exc

    if resp.status_code in (401, 403):
        raise ReadPermissionError(
            f"LinkedIn refused to list posts ({resp.status_code}): {resp.text[:200]}"
        )
    if resp.status_code >= 400:
        raise APIError(f"Listing posts failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    rows = data.get("elements", []) if isinstance(data, dict) else []
    out = []
    for row in rows:
        urn = row.get("id", "")
        out.append(
            {
                "urn": urn if str(urn).startswith("urn:") else f"urn:li:activity:{urn}",
                "text": row.get("commentary", "") or "",
            }
        )
    return out
