"""Publishing to LinkedIn and Instagram. DRY_RUN=true simulates everything (default)."""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import oauth
from .config import MEDIA_DIR, settings

log = logging.getLogger("publisher")


@dataclass
class Result:
    ok: bool
    external_id: str = ""
    url: str = ""
    error: str = ""
    simulated: bool = False


# ---------------------------------------------------------------- image helpers
def is_remote(image_file: str) -> bool:
    return image_file.startswith(("http://", "https://"))


def public_image_url(image_file: str) -> str:
    return image_file if is_remote(image_file) else f"{settings.public_base_url.rstrip('/')}/media/{image_file}"


async def image_bytes(image_file: str) -> tuple[bytes, str]:
    if is_remote(image_file):
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.get(image_file)
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "image/jpeg")
    path = Path(MEDIA_DIR / image_file)
    ctype = "image/png" if path.suffix == ".png" else "image/jpeg"
    return path.read_bytes(), ctype


def _err(resp: httpx.Response) -> str:
    return f"HTTP {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------- LinkedIn
def _li_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": settings.linkedin_api_version,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


async def linkedin_author(client: httpx.AsyncClient, token: str, urn: str) -> str:
    if urn:
        return urn
    r = await client.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise RuntimeError("Could not detect author (token needs openid+profile scopes, or set LINKEDIN_AUTHOR_URN): " + _err(r))
    return f"urn:li:person:{r.json()['sub']}"


async def publish_linkedin(text: str, image_file: str, alt_text: str) -> Result:
    if settings.dry_run:
        await asyncio.sleep(0.3)
        return Result(True, "dry-run-linkedin", "", simulated=True)
    token, urn = oauth.linkedin_creds()
    if not token:
        return Result(False, error="LinkedIn is not connected (or the token expired). Open Brand & setup and press Connect.")
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            author = await linkedin_author(c, token, urn)
            body = {
                "author": author,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            if image_file:
                init = await c.post(
                    "https://api.linkedin.com/rest/images?action=initializeUpload",
                    headers=_li_headers(token),
                    json={"initializeUploadRequest": {"owner": author}},
                )
                if init.status_code != 200:
                    return Result(False, error="Image init failed - " + _err(init))
                value = init.json()["value"]
                data, ctype = await image_bytes(image_file)
                up = await c.put(value["uploadUrl"], content=data, headers={
                    "Authorization": f"Bearer {token}", "Content-Type": ctype})
                if up.status_code not in (200, 201):
                    return Result(False, error="Image upload failed - " + _err(up))
                body["content"] = {"media": {"id": value["image"], **({"altText": alt_text[:4086]} if alt_text else {})}}
            r = await c.post("https://api.linkedin.com/rest/posts", headers=_li_headers(token), json=body)
            if r.status_code not in (200, 201):
                return Result(False, error=_err(r))
            urn = r.headers.get("x-restli-id", "")
            return Result(True, urn, f"https://www.linkedin.com/feed/update/{urn}/" if urn else "")
    except Exception as e:  # network, bad file, etc.
        log.exception("linkedin publish failed")
        return Result(False, error=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- Instagram
async def publish_instagram(caption: str, image_file: str) -> Result:
    if settings.dry_run:
        await asyncio.sleep(0.3)
        return Result(True, "dry-run-instagram", "", simulated=True)
    ig_token, ig_user = oauth.instagram_creds()
    if not (ig_token and ig_user):
        return Result(False, error="Instagram is not connected (or the token expired). Open Brand & setup and press Connect.")
    if not image_file:
        return Result(False, error="Instagram posts need an image")
    url = public_image_url(image_file)
    if not is_remote(image_file) and ("localhost" in url or "127.0.0.1" in url):
        return Result(False, error="Instagram must download the image from a public URL. Set PUBLIC_BASE_URL to a tunnel "
                                   "(ngrok / cloudflared) pointing at this backend, or use a generated image URL.")
    base = f"https://graph.facebook.com/{settings.graph_api_version}"
    token = {"access_token": ig_token}
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            create = await c.post(f"{base}/{ig_user}/media",
                                  data={"image_url": url, "caption": caption, **token})
            if create.status_code != 200:
                return Result(False, error="Container failed - " + _err(create))
            cid = create.json()["id"]
            for _ in range(15):  # wait until Instagram finished processing the image
                st = await c.get(f"{base}/{cid}", params={"fields": "status_code", **token})
                code = st.json().get("status_code") if st.status_code == 200 else None
                if code == "FINISHED":
                    break
                if code in ("ERROR", "EXPIRED"):
                    return Result(False, error=f"Instagram processing status: {code}")
                await asyncio.sleep(2)
            pub = await c.post(f"{base}/{ig_user}/media_publish", data={"creation_id": cid, **token})
            if pub.status_code != 200:
                return Result(False, error="Publish failed - " + _err(pub))
            media_id = pub.json()["id"]
            link = await c.get(f"{base}/{media_id}", params={"fields": "permalink", **token})
            permalink = link.json().get("permalink", "") if link.status_code == 200 else ""
            return Result(True, media_id, permalink)
    except Exception as e:
        log.exception("instagram publish failed")
        return Result(False, error=f"{type(e).__name__}: {e}")
