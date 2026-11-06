"""Text via OpenRouter (free models), images via Pollinations (free, keyless) or OpenRouter."""
import base64
import json
import logging
import re
import uuid
from urllib.parse import quote

import httpx

from .config import MEDIA_DIR, PROMPTS_DIR, settings
from .captions import short_caption
from .seo import normalize_tags

log = logging.getLogger("ai")


class AIError(Exception):
    pass


# ---------------------------------------------------------------- prompts
def load_prompt(name: str) -> str:
    override = getattr(settings, f"{name}_prompt", "")
    if override.strip():
        return override.replace("\\n", "\n")
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(template: str, ctx: dict) -> str:
    for k, v in ctx.items():
        template = template.replace("{{" + k + "}}", str(v) if v not in (None, "") else "n/a")
    return template


# ---------------------------------------------------------------- OpenRouter text
def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise AIError("Model did not return JSON")
    return json.loads(text[start : end + 1])


async def chat_json(prompt: str) -> dict:
    if not settings.openrouter_api_key:
        raise AIError("OPENROUTER_API_KEY is not set")
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": settings.openrouter_referer,
        "X-Title": settings.openrouter_app_title,
    }
    errors = []
    async with httpx.AsyncClient(timeout=120) as client:
        for model in settings.text_models:
            try:
                r = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers=headers,
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
                )
                if r.status_code != 200:
                    errors.append(f"{model}: HTTP {r.status_code} {r.text[:120]}")
                    continue
                content = r.json()["choices"][0]["message"]["content"] or ""
                return _extract_json(content)
            except (httpx.HTTPError, KeyError, ValueError, AIError) as e:
                errors.append(f"{model}: {e}")
    raise AIError("All models failed - " + " | ".join(errors))


# ---------------------------------------------------------------- post generation
def _fallback_post(topic: str) -> dict:
    """Used when no API key is configured so the app still works offline."""
    b = settings
    kw = (b.keywords or [topic])[0]
    cta = b.brand_cta or "What is your take? Tell me in the comments."
    return {
        "linkedin_post": (
            f"{topic} - here is what we learned about {kw} at {b.brand_name}.\n\n"
            f"Most teams overcomplicate this. Start with one clear goal and measure it weekly.\n\n"
            f"Three things that actually move the needle:\n"
            f"1. Be specific about who you help.\n2. Show proof, not promises.\n3. Stay consistent.\n\n{cta}"
        ),
        "instagram_caption": (
            f"{topic} ✨\n\nA quick reminder from {b.brand_name}: {kw} works best when you keep it simple, "
            f"specific and consistent.\n\nSave this for later and tell us what you would add.\n\n{cta}"
        ),
        "hashtags": b.hashtags[:5] or ["growth", "marketing", "tips"],
        "keywords": b.keywords[:3],
        "image_caption": short_caption(topic),
        "image_prompt": f"Minimal editorial illustration representing {topic}, {kw}, bold shapes, brand colours",
        "alt_text": f"Illustration about {topic} related to {kw}",
    }


async def generate_post(topic: str, platforms: list[str], extra: str = "") -> dict:
    ctx = {**settings.brand_profile(), "topic": topic, "extra": extra, "platforms": ", ".join(platforms)}
    source, warning = "ai", ""
    try:
        data = await chat_json(render(load_prompt("post"), ctx))
    except AIError as e:
        log.warning("AI generation failed, using template: %s", e)
        data, source, warning = _fallback_post(topic), "template", str(e)
    return {
        "linkedin_text": str(data.get("linkedin_post") or data.get("linkedin_text") or "").strip(),
        "instagram_caption": str(data.get("instagram_caption") or "").strip(),
        "hashtags": normalize_tags(data.get("hashtags") or settings.hashtags)[:8],
        "keywords": [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()][:8],
        "image_caption": " ".join(str(data.get("image_caption") or "").split())[:90],
        "image_prompt": str(data.get("image_prompt") or "").strip(),
        "alt_text": str(data.get("alt_text") or "").strip(),
        "source": source,
        "warning": warning,
    }


async def generate_ideas(count: int, recent: list[str]) -> list[dict]:
    ctx = {**settings.brand_profile(), "count": count, "recent": "; ".join(recent[-15:]) or "none"}
    try:
        data = await chat_json(render(load_prompt("ideas"), ctx))
        ideas = [i for i in data.get("ideas", []) if isinstance(i, dict) and i.get("title")]
        if ideas:
            return ideas[:count]
    except AIError as e:
        log.warning("Idea generation failed, using template: %s", e)
    pillars = settings.pillars or ["Tips", "Stories", "Behind the scenes"]
    kws = settings.keywords or [settings.brand_name]
    return [
        {"title": f"{pillars[i % len(pillars)]}: {kws[i % len(kws)]}", "angle": "", "pillar": pillars[i % len(pillars)]}
        for i in range(count)
    ]


# ---------------------------------------------------------------- images
def _save_image(data: bytes, ext: str = "jpg") -> str:
    MEDIA_DIR.mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.{ext}"
    (MEDIA_DIR / name).write_bytes(data)
    return name


async def _pollinations(prompt: str) -> str:
    url = (
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width={settings.image_width}&height={settings.image_height}&nologo=true&model=flux&seed={uuid.uuid4().int % 100000}"
    )
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(url)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        raise AIError(f"Pollinations failed: HTTP {r.status_code}")
    return _save_image(r.content, "jpg")


async def _openrouter_image(prompt: str) -> str:
    if not settings.openrouter_api_key:
        raise AIError("OPENROUTER_API_KEY is not set")
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_image_model,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
            },
        )
    if r.status_code != 200:
        raise AIError(f"OpenRouter image HTTP {r.status_code}: {r.text[:150]}")
    try:
        url = r.json()["choices"][0]["message"]["images"][0]["image_url"]["url"]
        header, b64 = url.split(",", 1)
        ext = "png" if "png" in header else "jpg"
        return _save_image(base64.b64decode(b64), ext)
    except (KeyError, IndexError, ValueError) as e:
        raise AIError(f"OpenRouter returned no image: {e}")


async def generate_image(prompt: str) -> str:
    """Returns the saved filename inside media/."""
    full = f"{prompt}. {settings.image_style}".strip()
    provider = settings.image_provider.lower()
    if provider == "none":
        raise AIError("IMAGE_PROVIDER=none")
    order = [_openrouter_image, _pollinations] if provider == "openrouter" else [_pollinations]
    errors = []
    for fn in order:
        try:
            return await fn(full)
        except (AIError, httpx.HTTPError) as e:
            errors.append(str(e))
    raise AIError(" | ".join(errors))
