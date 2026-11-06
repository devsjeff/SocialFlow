import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from . import ai, captions, publishers
from .config import settings
from .models import Post, engine, utcnow
from .seo import compose, score_post

log = logging.getLogger("service")

WRITING: set[int] = set()  # drafts the background writer is working on right now

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------------------------------------------- serialization
def iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def serialize(post: Post) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "notes": post.notes,
        "platforms": post.platforms,
        "linkedin_text": post.linkedin_text,
        "instagram_caption": post.instagram_caption,
        "hashtags": post.hashtags,
        "keywords": post.keywords,
        "image_prompt": post.image_prompt,
        "image_file": post.image_file,
        "image_url": (post.image_file if publishers.is_remote(post.image_file) else f"/media/{post.image_file}") if post.image_file else "",
        "alt_text": post.alt_text,
        "image_caption": post.image_caption,
        "image_base": post.image_base,
        "scheduled_at": iso(post.scheduled_at),
        "status": post.status,
        "writing": post.id in WRITING,
        "results": post.results or {},
        "seo": score_post(post),
        "created_at": iso(post.created_at),
        "updated_at": iso(post.updated_at),
    }


# ---------------------------------------------------------------- publishing
def _text_for(post: Post, platform: str) -> str:
    base = post.linkedin_text if platform == "linkedin" else post.instagram_caption
    return compose(base, post.hashtags)


async def fill_post(post_id: int, *, write: bool = True, image: bool = True) -> list[str]:
    """Create whatever is missing (text from the topic, image from the prompt). Never overwrites existing content.

    Returns human-readable warnings for things that could not be created.
    """
    with Session(engine) as s:
        p = s.get(Post, post_id)
        if not p:
            return []
        snap = {"title": p.title, "notes": p.notes, "platforms": list(p.platforms), "li": p.linkedin_text,
                "ig": p.instagram_caption, "image": p.image_file, "prompt": p.image_prompt, "alt": p.alt_text, "caption": p.image_caption,
                "tags": list(p.hashtags), "kws": list(p.keywords)}

    def missing(pl: str) -> bool:
        return not (snap["li"] if pl == "linkedin" else snap["ig"]).strip()

    warnings: list[str] = []
    upd: dict = {}
    gen_caption = ""
    if write and snap["title"].strip() and any(missing(pl) for pl in snap["platforms"]):
        g = await ai.generate_post(snap["title"].strip(), snap["platforms"], snap["notes"])
        if g["source"] != "ai":  # never auto-publish the generic offline template
            warnings.append("AI writing failed: " + (g["warning"] or "unknown error")[:160])
        else:
            if not snap["li"].strip():
                upd["linkedin_text"] = g["linkedin_text"]
            if not snap["ig"].strip():
                upd["instagram_caption"] = g["instagram_caption"]
            if not snap["tags"]:
                upd["hashtags"] = g["hashtags"]
            if not snap["kws"]:
                upd["keywords"] = g["keywords"]
            if not snap["prompt"].strip():
                upd["image_prompt"] = g["image_prompt"]
            if not snap["alt"].strip():
                upd["alt_text"] = g["alt_text"]
            gen_caption = g.get("image_caption", "")
    if image and not snap["image"]:
        prompt = upd.get("image_prompt") or snap["prompt"] or snap["title"]
        if prompt.strip():
            try:
                base = await ai.generate_image(prompt)
                upd["image_base"] = base
                upd["image_file"] = base
                if not (upd.get("alt_text") or snap["alt"]).strip():
                    upd["alt_text"] = snap["title"][:200]
                # your own caption is always drawn; IMAGE_CAPTION only controls the automatic one
                auto = (gen_caption or captions.short_caption(snap["title"])) if settings.image_caption else ""
                caption = snap["caption"] or auto
                if caption:  # small headline drawn on the photo
                    try:
                        upd["image_file"] = captions.render(base, caption)
                        upd["image_caption"] = caption
                    except Exception as e:
                        warnings.append(f"Caption not drawn: {e}"[:120])
            except Exception as e:
                warnings.append(f"Image could not be created: {e}"[:200])
    if upd:
        with Session(engine) as s:
            p = s.get(Post, post_id)
            if p:
                for k, v in upd.items():  # don't clobber edits made while the AI was busy
                    if not getattr(p, k):
                        setattr(p, k, v)
                p.updated_at = utcnow()
                s.add(p)
                s.commit()
    return warnings


async def write_drafts(ids: list[int]) -> None:
    """Background writer used by Auto-plan: text + image for each draft, one after another (free models are rate-limited)."""
    WRITING.update(ids)
    for pid in ids:
        try:
            await fill_post(pid)
        except Exception:
            log.exception("writing draft %s failed", pid)
        finally:
            WRITING.discard(pid)


async def publish_post(post_id: int) -> None:
    """Publish every selected platform that has not already succeeded. Missing text/image are created first."""
    with Session(engine) as s:
        post = s.get(Post, post_id)
        if not post or post.status == "publishing":
            return
        post.status = "publishing"
        s.add(post)
        s.commit()

    try:
        warnings = await fill_post(post_id, write=settings.auto_write, image=settings.auto_image)
    except Exception as e:
        log.exception("auto-fill failed")
        warnings = [f"Auto-create failed: {e}"[:200]]
    note = f" ({'; '.join(warnings)})" if warnings else ""

    with Session(engine) as s:
        post = s.get(Post, post_id)
        if not post:
            return
        platforms = list(post.platforms)
        results = dict(post.results or {})
        image, alt = post.image_file, post.alt_text
        texts = {p: _text_for(post, p) for p in platforms}
        # hashtags alone are not a post: judge emptiness on the body text only
        empty = {p: not (post.linkedin_text if p == "linkedin" else post.instagram_caption).strip() for p in platforms}

    for p in platforms:
        if results.get(p, {}).get("ok"):
            continue
        if empty[p]:
            res = publishers.Result(False, error="Text is empty" + note)
        elif p == "linkedin":
            res = await publishers.publish_linkedin(texts[p], image, alt)
        elif p == "instagram":
            res = await publishers.publish_instagram(texts[p], image)
        else:
            res = publishers.Result(False, error=f"Unknown platform {p}")
        err = res.error + (note if res.error and not image else "")
        results[p] = {"ok": res.ok, "id": res.external_id, "url": res.url, "error": err,
                      "simulated": res.simulated, "at": iso(utcnow())}

    oks = [bool(results.get(p, {}).get("ok")) for p in platforms]
    status = "published" if all(oks) else "partial" if any(oks) else "failed"
    with Session(engine) as s:
        post = s.get(Post, post_id)
        if post:
            post.results = results
            post.status = status
            post.updated_at = utcnow()
            s.add(post)
            s.commit()
    log.info("post %s -> %s", post_id, status)


async def run_due() -> None:
    with Session(engine) as s:
        ids = s.exec(select(Post.id).where(Post.status == "scheduled", Post.scheduled_at <= utcnow())).all()
    for pid in ids:
        await publish_post(pid)


async def scheduler_loop() -> None:
    # recover posts that were mid-publish when the server stopped
    with Session(engine) as s:
        for p in s.exec(select(Post).where(Post.status == "publishing")).all():
            p.status = "scheduled"
            s.add(p)
        s.commit()
    while True:
        try:
            await run_due()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)


# ---------------------------------------------------------------- planning
def tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_timezone)
    except Exception:
        return ZoneInfo("UTC")


def next_slots(count: int, start: datetime | None = None, taken: set[datetime] | None = None) -> list[datetime]:
    """Next `count` free posting slots (UTC naive), based on POSTING_DAYS / POSTING_TIMES in APP_TIMEZONE."""
    zone = tz()
    now_local = (start or utcnow()).replace(tzinfo=timezone.utc).astimezone(zone)
    times = []
    for t in settings.times or ["09:30"]:
        try:
            h, m = t.split(":")
            times.append(time(int(h), int(m)))
        except ValueError:
            continue
    days = [d for d in settings.days if d in DAYS] or DAYS
    taken = taken or set()
    out: list[datetime] = []
    day: date = now_local.date()
    for _ in range(366):
        if DAYS[day.weekday()] in days:
            for t in times:
                local = datetime.combine(day, t, tzinfo=zone)
                utc = local.astimezone(timezone.utc).replace(tzinfo=None)
                if local > now_local and utc not in taken:
                    out.append(utc)
                    if len(out) >= count:
                        return out
        day += timedelta(days=1)
    return out
