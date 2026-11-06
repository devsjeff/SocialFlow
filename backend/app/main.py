import asyncio
import logging
import uuid
from pathlib import Path
from collections import Counter
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import ai, captions, oauth, service
from .config import MEDIA_DIR, settings
from .models import Post, get_session, init_db, utcnow
from .seo import normalize_tags, score_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
Platform = Literal["linkedin", "instagram"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    MEDIA_DIR.mkdir(exist_ok=True)
    init_db()
    task = asyncio.create_task(service.scheduler_loop())
    yield
    task.cancel()


app = FastAPI(title="Post Scheduler API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_methods=["*"], allow_headers=["*"])
MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


# ---------------------------------------------------------------- schemas
class PostIn(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    platforms: Optional[list[Platform]] = None
    linkedin_text: Optional[str] = None
    instagram_caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    image_prompt: Optional[str] = None
    image_file: Optional[str] = None
    image_base: Optional[str] = None
    image_caption: Optional[str] = None
    alt_text: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[Literal["draft", "scheduled"]] = None


def apply(post: Post, data: PostIn) -> None:
    fields = data.model_dump(exclude_unset=True)
    if "scheduled_at" in fields:
        post.scheduled_at = service.to_utc_naive(fields.pop("scheduled_at"))
    for key in ("hashtags",):
        if key in fields:
            fields[key] = normalize_tags(fields[key] or [])
    if "platforms" in fields and not fields["platforms"]:
        raise HTTPException(422, "Pick at least one platform")
    for k, v in fields.items():
        if v is not None:
            setattr(post, k, v)
    if post.status == "scheduled" and not post.scheduled_at:
        raise HTTPException(422, "Pick a date and time to schedule")
    post.updated_at = utcnow()


def get_or_404(session: Session, post_id: int) -> Post:
    post = session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    return post


# ---------------------------------------------------------------- basics
@app.get("/api/health")
def health():
    return {"ok": True, "time": service.iso(utcnow())}


@app.get("/api/config")
def config():
    return {
        "brand": settings.brand_profile(),
        "keywords": settings.keywords,
        "hashtags": settings.hashtags,
        "pillars": settings.pillars,
        "timezone": settings.app_timezone,
        "posting_times": settings.times,
        "posting_days": settings.days,
        "default_platforms": settings.platforms,
        "dry_run": settings.dry_run,
        "auto_write": settings.auto_write,
        "auto_image": settings.auto_image,
        "image_caption": settings.image_caption,
        "ai": {
            "configured": bool(settings.openrouter_api_key),
            "models": settings.text_models,
            "image_provider": settings.image_provider,
            "image_model": settings.openrouter_image_model if settings.image_provider == "openrouter" else "pollinations/flux",
        },
        "integrations": {p: oauth.account_status(p)["connected"] for p in oauth.PLATFORMS},
        "accounts": {p: oauth.account_status(p) for p in oauth.PLATFORMS},
        "oauth": {p: oauth.readiness(p) for p in oauth.PLATFORMS},
        "public_url_is_local": any(h in settings.public_base_url for h in ("localhost", "127.0.0.1")),
    }


# ---------------------------------------------------------------- connect accounts (OAuth)
def _platform(platform: str) -> str:
    if platform not in oauth.PLATFORMS:
        raise HTTPException(404, "Unknown platform")
    return platform


@app.get("/api/oauth/{platform}/start")
def oauth_start(platform: str):
    try:
        return RedirectResponse(oauth.authorize_url(_platform(platform)), status_code=302)
    except oauth.OAuthError as e:
        raise HTTPException(400, str(e))


@app.get("/api/oauth/{platform}/callback")
async def oauth_callback(platform: str, code: Optional[str] = None, state: Optional[str] = None,
                         error: Optional[str] = None, error_description: Optional[str] = None):
    back = f"{settings.frontend_url.rstrip('/')}/settings"

    def fail(msg: str):
        return RedirectResponse(f"{back}?{urlencode({'error': msg})}", status_code=302)

    _platform(platform)
    if error:
        return fail(error_description or error)
    if not code or not state or not oauth.consume_state(state, platform):
        return fail("The sign-in session expired or was invalid. Please press Connect again.")
    try:
        await oauth.complete(platform, code)
    except (oauth.OAuthError, httpx.HTTPError) as e:
        return fail(str(e))
    return RedirectResponse(f"{back}?{urlencode({'connected': platform})}", status_code=302)


@app.delete("/api/oauth/{platform}")
def oauth_disconnect(platform: str):
    oauth.disconnect(_platform(platform))
    return {"ok": True}


# ---------------------------------------------------------------- posts CRUD
@app.get("/api/posts")
def list_posts(start: Optional[datetime] = None, end: Optional[datetime] = None,
               status: Optional[str] = None, session: Session = Depends(get_session)):
    q = select(Post).order_by(Post.scheduled_at, Post.id)
    if start:
        q = q.where(Post.scheduled_at >= service.to_utc_naive(start))
    if end:
        q = q.where(Post.scheduled_at < service.to_utc_naive(end))
    if status:
        q = q.where(Post.status == status)
    return [service.serialize(p) for p in session.exec(q).all()]


@app.post("/api/posts")
def create_post(data: PostIn, session: Session = Depends(get_session)):
    post = Post(platforms=settings.platforms or ["linkedin", "instagram"], hashtags=settings.hashtags[:5])
    apply(post, data)
    session.add(post)
    session.commit()
    session.refresh(post)
    return service.serialize(post)


@app.get("/api/posts/{post_id}")
def get_post(post_id: int, session: Session = Depends(get_session)):
    return service.serialize(get_or_404(session, post_id))


@app.put("/api/posts/{post_id}")
def update_post(post_id: int, data: PostIn, session: Session = Depends(get_session)):
    post = get_or_404(session, post_id)
    if post.status in ("publishing", "published"):
        raise HTTPException(409, f"A {post.status} post can't be edited")
    apply(post, data)  # failed/partial posts keep their status until re-scheduled or retried
    session.add(post)
    session.commit()
    session.refresh(post)
    return service.serialize(post)


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int, session: Session = Depends(get_session)):
    post = get_or_404(session, post_id)
    session.delete(post)
    session.commit()
    return {"ok": True}


@app.post("/api/posts/{post_id}/publish")
async def publish_now(post_id: int, session: Session = Depends(get_session)):
    post = get_or_404(session, post_id)
    if post.status == "publishing":
        raise HTTPException(409, "Already publishing")
    if post.status == "published":
        raise HTTPException(409, "Already published")
    session.close()
    await service.publish_post(post_id)
    with Session(service.engine) as s:
        return service.serialize(s.get(Post, post_id))


@app.post("/api/seo/score")
def seo_score(data: PostIn):
    tmp = Post(
        platforms=data.platforms or settings.platforms,
        linkedin_text=data.linkedin_text or "",
        instagram_caption=data.instagram_caption or "",
        hashtags=normalize_tags(data.hashtags or []),
        keywords=data.keywords or [],
        image_file=data.image_file or "",
        alt_text=data.alt_text or "",
    )
    return score_post(tmp)


# ---------------------------------------------------------------- AI
class GenerateIn(BaseModel):
    topic: str = Field(min_length=2)
    platforms: list[Platform] = ["linkedin", "instagram"]
    extra: str = ""


@app.post("/api/ai/generate")
async def ai_generate(data: GenerateIn):
    return await ai.generate_post(data.topic, data.platforms, data.extra)


class ImageIn(BaseModel):
    prompt: str = Field(min_length=3)
    caption: str = ""  # small headline to draw on the photo (empty = none)


def _image_payload(base: str, file: str) -> dict:
    return {"image_base": base, "image_file": file, "image_url": f"/media/{file}"}


@app.post("/api/ai/image")
async def ai_image(data: ImageIn):
    try:
        base = await ai.generate_image(data.prompt)
    except ai.AIError as e:
        raise HTTPException(502, f"Image generation failed: {e}")
    try:
        return _image_payload(base, captions.render(base, data.caption))
    except Exception as e:
        raise HTTPException(500, f"Caption could not be drawn: {e}")


class CaptionIn(BaseModel):
    image_base: str = Field(min_length=3)
    caption: str = ""


@app.post("/api/image/caption")
def image_caption(data: CaptionIn):
    """Re-draw the caption on the clean image. Empty caption returns the clean image."""
    try:
        return _image_payload(Path(data.image_base).name, captions.render(data.image_base, data.caption))
    except FileNotFoundError:
        raise HTTPException(404, "Original image not found, generate or upload it again")
    except Exception as e:
        raise HTTPException(500, f"Caption could not be drawn: {e}")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg"):
        raise HTTPException(422, "Only PNG or JPG images (Instagram does not accept WebP)")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 8 MB)")
    name = f"{uuid.uuid4().hex[:12]}.{'jpg' if ext == 'jpeg' else ext}"
    (MEDIA_DIR / name).write_bytes(data)
    return _image_payload(name, name)


class PlanIn(BaseModel):
    count: int = Field(default=7, ge=1, le=30)
    platforms: Optional[list[Platform]] = None  # default: DEFAULT_PLATFORMS from .env
    write: bool = False  # also write text + image for every draft in the background


_background: set = set()  # keeps references so background tasks are not garbage-collected


@app.post("/api/plan")
async def auto_plan(data: PlanIn, session: Session = Depends(get_session)):
    """Ask the AI for topic ideas and drop them as drafts on the next free posting slots."""
    existing = session.exec(select(Post)).all()
    taken = {p.scheduled_at for p in existing if p.scheduled_at}
    ideas = await ai.generate_ideas(data.count, [p.title for p in existing if p.title])
    slots = service.next_slots(len(ideas), taken=taken)
    platforms = data.platforms or settings.platforms or ["linkedin"]
    created = []
    for idea, slot in zip(ideas, slots):
        post = Post(
            title=str(idea["title"])[:200],
            notes=" - ".join(x for x in (idea.get("pillar"), idea.get("angle")) if x),
            platforms=platforms,
            hashtags=settings.hashtags[:5],
            scheduled_at=slot,
            status="draft",
        )
        session.add(post)
        created.append(post)
    session.commit()
    for p in created:
        session.refresh(p)
    if data.write and created:
        service.WRITING.update(p.id for p in created)  # show "writing" immediately
        task = asyncio.create_task(service.write_drafts([p.id for p in created]))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return [service.serialize(p) for p in created]


# ---------------------------------------------------------------- dashboard
@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    posts = session.exec(select(Post)).all()
    now = utcnow()
    counts = Counter(p.status for p in posts)
    upcoming = sorted((p for p in posts if p.status == "scheduled" and p.scheduled_at and p.scheduled_at >= now),
                      key=lambda p: p.scheduled_at)[:6]
    attention = [p for p in posts if p.status in ("failed", "partial")]
    drafts = sorted((p for p in posts if p.status == "draft"),
                    key=lambda p: (p.scheduled_at is None, p.scheduled_at or now))[:8]
    drafts_no_content = [p for p in posts if p.status == "draft" and not (p.linkedin_text or p.instagram_caption)]
    seo_scores = [score_post(p)["score"] for p in posts if p.status in ("scheduled", "published", "draft")
                  and (p.linkedin_text or p.instagram_caption)]
    by_platform = Counter(pl for p in posts if p.status in ("scheduled", "published", "partial") for pl in p.platforms)
    # next 14 days activity (UTC days, good enough for a sparkline)
    today = now.date()
    activity = []
    for i in range(14):
        d = today + timedelta(days=i)
        day_posts = [p for p in posts if p.scheduled_at and p.scheduled_at.date() == d]
        activity.append({"date": d.isoformat(), "count": len(day_posts)})
    return {
        "counts": {s: counts.get(s, 0) for s in ("draft", "scheduled", "published", "partial", "failed")},
        "total": len(posts),
        "upcoming": [service.serialize(p) for p in upcoming],
        "attention": [service.serialize(p) for p in attention][:5],
        "drafts": [service.serialize(p) for p in drafts],
        "writing": len(service.WRITING),
        "empty_drafts": len(drafts_no_content),
        "avg_seo": round(sum(seo_scores) / len(seo_scores)) if seo_scores else None,
        "by_platform": {"linkedin": by_platform.get("linkedin", 0), "instagram": by_platform.get("instagram", 0)},
        "activity": activity,
    }
