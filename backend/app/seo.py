"""Lightweight, explainable SEO / reach checks for LinkedIn and Instagram posts.

Both platforms index post text (LinkedIn search + Google, Instagram search), so the
rules reward: keyword in the hook, a few relevant hashtags, a clear CTA, scannable
formatting, alt text on the image, and staying inside the character limits.
"""
import re

from .config import settings

CTA_WORDS = (
    "comment", "share", "follow", "save", "dm", "message", "book", "download", "subscribe",
    "learn more", "link in bio", "click", "join", "sign up", "try", "tell me", "let me know",
    "what do you think", "agree", "reply", "visit", "contact",
)

LIMITS = {"linkedin": 3000, "instagram": 2200}
HOOK_LEN = {"linkedin": 210, "instagram": 125}  # chars visible before "see more"


def normalize_tags(tags: list[str]) -> list[str]:
    out, seen = [], set()
    for t in tags:
        t = re.sub(r"[^\w]", "", str(t).strip().lstrip("#"))
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def compose(text: str, hashtags: list[str]) -> str:
    tags = " ".join("#" + t for t in normalize_tags(hashtags))
    return f"{text.strip()}\n\n{tags}".strip() if tags else text.strip()


def _hits(text: str, keywords: list[str]) -> list[str]:
    low = text.lower()
    return [k for k in keywords if k and k.lower() in low]


def score_platform(platform: str, text: str, hashtags: list[str], keywords: list[str],
                   has_image: bool, alt_text: str) -> dict:
    kws = [k for k in dict.fromkeys([*keywords, *settings.keywords]) if k]
    text = text.strip()
    hook = text[: HOOK_LEN[platform]]
    n_tags = len(normalize_tags(hashtags))
    length = len(compose(text, hashtags))
    paragraphs = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    avg_par = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
    low = text.lower()

    checks: list[tuple[str, bool, str, int]] = []  # label, passed, tip, weight

    checks.append((
        f"Keyword in first {HOOK_LEN[platform]} characters",
        bool(_hits(hook, kws)) if kws else False,
        "Put your main keyword inside the hook - it is what search and the feed preview show."
        if kws else "Add BRAND_KEYWORDS in .env (or post keywords) so this can be checked.",
        20,
    ))
    checks.append((
        "Uses 2+ target keywords naturally",
        len(_hits(text, kws)) >= 2,
        "Work at least two target keywords into the copy (no stuffing).",
        10,
    ))
    if platform == "linkedin":
        checks.append(("Good length (500-2000 chars)", 500 <= len(text) <= 2000,
                       "LinkedIn posts with 500-2000 characters tend to earn the most dwell time.", 15))
        checks.append(("3-5 hashtags", 3 <= n_tags <= 5,
                       "Use 3-5 specific hashtags at the end, not 10+ generic ones.", 15))
    else:
        checks.append(("Caption has substance (150+ chars)", len(text) >= 150,
                       "Instagram search reads captions - give it a real, keyword-rich description.", 15))
        checks.append(("3-5 hashtags", 3 <= n_tags <= 5,
                       "Instagram now favours a few relevant hashtags (3-5) over big blocks.", 15))
    checks.append((
        "Scannable (short paragraphs / line breaks)",
        avg_par <= 280 and (len(paragraphs) >= 3 or len(text) < 200),
        "Break text into short lines; walls of text get skipped.",
        10,
    ))
    checks.append((
        "Clear call to action",
        "?" in text[-300:] or any(w in low for w in CTA_WORDS),
        "End with a question or a CTA (comment, save, follow, book...).",
        10,
    ))
    checks.append((
        "Image attached" if platform == "instagram" else "Image attached (boosts reach)",
        has_image,
        "Instagram requires an image." if platform == "instagram" else "Posts with a visual get noticeably more impressions.",
        10 if platform == "linkedin" else 15,
    ))
    checks.append((
        "Image alt text (accessibility + SEO)",
        bool(alt_text.strip()) if has_image else False,
        "Describe the image in one sentence with a keyword - used by screen readers and search.",
        5 if platform == "linkedin" else 5,
    ))
    checks.append((
        f"Within {LIMITS[platform]}-character limit",
        0 < length <= LIMITS[platform],
        f"{platform.title()} cuts posts over {LIMITS[platform]} characters.",
        5 if platform == "linkedin" else 5,
    ))

    total = sum(c[3] for c in checks)
    got = sum(c[3] for c in checks if c[1])
    return {
        "platform": platform,
        "score": round(100 * got / total),
        "chars": length,
        "checks": [{"label": l, "passed": p, "tip": t} for l, p, t, _ in checks],
    }


def score_post(post) -> dict:
    """Score a Post (or any object with the same attributes) for each selected platform."""
    has_image = bool(post.image_file)
    per = []
    for p in post.platforms:
        if p == "linkedin":
            text = post.linkedin_text
        elif p == "instagram":
            text = post.instagram_caption
        else:
            continue
        per.append(score_platform(p, text, post.hashtags, post.keywords, has_image, post.alt_text))
    overall = round(sum(x["score"] for x in per) / len(per)) if per else 0
    return {"score": overall, "platforms": per}
