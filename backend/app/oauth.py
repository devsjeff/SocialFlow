"""One-click "Connect" flows for LinkedIn and Instagram, plus credential lookup.

Credentials resolve as: connected account in the DB first, then the token pasted in .env.
"""
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from .config import settings
from .models import Connection, engine, utcnow

PLATFORMS = ("linkedin", "instagram")
LINKEDIN_SCOPES = "openid profile w_member_social"
STATE_TTL = 600  # seconds the user has to finish the consent screen

_states: dict[str, tuple[str, float]] = {}


class OAuthError(Exception):
    pass


def redirect_uri(platform: str) -> str:
    return f"{settings.oauth_redirect_base.rstrip('/')}/api/oauth/{platform}/callback"


def readiness(platform: str) -> dict:
    need = (
        {"LINKEDIN_CLIENT_ID": settings.linkedin_client_id, "LINKEDIN_CLIENT_SECRET": settings.linkedin_client_secret}
        if platform == "linkedin"
        else {"META_APP_ID": settings.meta_app_id, "META_APP_SECRET": settings.meta_app_secret}
    )
    missing = [k for k, v in need.items() if not v]
    return {"ready": not missing, "missing": missing, "redirect_uri": redirect_uri(platform)}


# ---------------------------------------------------------------- CSRF state
def _new_state(platform: str) -> str:
    now = time.time()
    for k in [k for k, (_, t) in _states.items() if now - t > STATE_TTL]:
        _states.pop(k, None)
    state = secrets.token_urlsafe(24)
    _states[state] = (platform, now)
    return state


def consume_state(state: str, platform: str) -> bool:
    entry = _states.pop(state, None)
    return bool(entry and entry[0] == platform and time.time() - entry[1] <= STATE_TTL)


# ---------------------------------------------------------------- step 1: send the user to the consent screen
def authorize_url(platform: str) -> str:
    r = readiness(platform)
    if not r["ready"]:
        raise OAuthError("Missing in .env: " + ", ".join(r["missing"]))
    state = _new_state(platform)
    if platform == "linkedin":
        q = {
            "response_type": "code", "client_id": settings.linkedin_client_id,
            "redirect_uri": redirect_uri(platform), "state": state, "scope": LINKEDIN_SCOPES,
        }
        return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(q)
    q = {
        "client_id": settings.meta_app_id, "redirect_uri": redirect_uri(platform), "state": state,
        "scope": settings.meta_scopes, "response_type": "code",
    }
    return f"https://www.facebook.com/{settings.graph_api_version}/dialog/oauth?" + urlencode(q)


# ---------------------------------------------------------------- step 2: trade the code for a token and save it
def _fail(resp: httpx.Response, what: str) -> OAuthError:
    try:
        body = resp.json()
        detail = body.get("error_description") or (body.get("error") or {}).get("message") or str(body)[:200]
    except Exception:
        detail = resp.text[:200]
    return OAuthError(f"{what} failed (HTTP {resp.status_code}): {detail}")


async def _complete_linkedin(code: str) -> Connection:
    async with httpx.AsyncClient(timeout=30) as c:
        tok = await c.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri("linkedin"),
                "client_id": settings.linkedin_client_id, "client_secret": settings.linkedin_client_secret,
            },
        )
        if tok.status_code != 200:
            raise _fail(tok, "LinkedIn token exchange")
        data = tok.json()
        access = data["access_token"]
        me = await c.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {access}"})
        if me.status_code != 200:
            raise _fail(me, "LinkedIn profile lookup")
        info = me.json()
    return Connection(
        platform="linkedin", access_token=access,
        expires_at=utcnow() + timedelta(seconds=int(data.get("expires_in", 5184000))),
        account_id=f"urn:li:person:{info['sub']}", account_name=info.get("name", "LinkedIn member"),
    )


async def _complete_instagram(code: str) -> Connection:
    base = f"https://graph.facebook.com/{settings.graph_api_version}"
    async with httpx.AsyncClient(timeout=30) as c:
        short = await c.get(f"{base}/oauth/access_token", params={
            "client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret,
            "redirect_uri": redirect_uri("instagram"), "code": code,
        })
        if short.status_code != 200:
            raise _fail(short, "Meta token exchange")
        long = await c.get(f"{base}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret, "fb_exchange_token": short.json()["access_token"],
        })
        if long.status_code != 200:
            raise _fail(long, "Meta long-lived token exchange")
        user_token = long.json()["access_token"]
        pages = await c.get(f"{base}/me/accounts", params={
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "limit": 50, "access_token": user_token,
        })
        if pages.status_code != 200:
            raise _fail(pages, "Facebook Pages lookup")
    for page in pages.json().get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            # A Page token obtained from a long-lived user token does not expire.
            return Connection(
                platform="instagram", access_token=page.get("access_token") or user_token, expires_at=None,
                account_id=ig["id"], account_name=f"@{ig.get('username', ig['id'])} (via {page.get('name', 'Page')})",
            )
    raise OAuthError(
        "No Instagram Business/Creator account found on the Facebook Pages you granted. Link the Instagram account "
        "to a Page, then connect again and tick that Page on the consent screen."
    )


async def complete(platform: str, code: str) -> Connection:
    conn = await (_complete_linkedin(code) if platform == "linkedin" else _complete_instagram(code))
    with Session(engine) as s:
        s.merge(conn)
        s.commit()
    return conn


def disconnect(platform: str) -> None:
    with Session(engine) as s:
        row = s.get(Connection, platform)
        if row:
            s.delete(row)
            s.commit()


# ---------------------------------------------------------------- credential lookup used by publishers
def _connection(platform: str) -> Connection | None:
    with Session(engine) as s:
        row = s.get(Connection, platform)
        if row and row.access_token and not (row.expires_at and row.expires_at <= utcnow()):
            return row
    return None


def linkedin_creds() -> tuple[str, str]:
    """(access_token, author_urn) - author may be '' if it must be detected from the token."""
    conn = _connection("linkedin")
    if conn:
        return conn.access_token, settings.linkedin_author_urn or conn.account_id
    return settings.linkedin_access_token, settings.linkedin_author_urn


def instagram_creds() -> tuple[str, str]:
    """(access_token, instagram_user_id)"""
    conn = _connection("instagram")
    if conn:
        return conn.access_token, settings.instagram_user_id or conn.account_id
    return settings.instagram_access_token, settings.instagram_user_id


def account_status(platform: str) -> dict:
    with Session(engine) as s:
        row = s.get(Connection, platform)
    if row:
        expired = bool(row.expires_at and row.expires_at <= utcnow())
        return {
            "connected": not expired, "expired": expired, "source": "oauth", "name": row.account_name,
            "expires_at": row.expires_at.replace(tzinfo=None).isoformat() + "Z" if row.expires_at else None,
        }
    token, ident = linkedin_creds() if platform == "linkedin" else instagram_creds()
    has = bool(token and (ident or platform == "linkedin"))
    return {"connected": has, "expired": False, "source": "env" if has else "", "name": "", "expires_at": None}
