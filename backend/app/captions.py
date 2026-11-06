"""Small caption overlay for post images (AI image models can't spell, so we draw the text ourselves)."""
import re
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import MEDIA_DIR, settings

_WIN = Path("C:/Windows/Fonts")
_LATIN = [
    _WIN / "segoeuib.ttf", _WIN / "arialbd.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
_DEVANAGARI = [_WIN / "NirmalaB.ttf", _WIN / "Nirmala.ttc", _WIN / "mangalb.ttf", *_LATIN]


def _font(size: int, text: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _DEVANAGARI if re.search(r"[\u0900-\u097F]", text) else _LATIN
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(text: str, font, max_width: float, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and font.getlength(lines[-1] + "…") > max_width:
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] += "…"
    return lines


def _hex(color: str, fallback=(124, 127, 247)) -> tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", color.strip())
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else fallback


def brand_tag() -> str:
    tag = settings.image_brand_tag
    return settings.brand_name if tag.strip().lower() == "auto" else tag.strip()


def render(base_file: str, caption: str) -> str:
    """Draw `caption` (+ small brand tag) on MEDIA_DIR/base_file. Returns the new file name.

    The original is never modified, so the caption can be edited or removed later.
    An empty caption returns the base file unchanged.
    """
    caption = " ".join(caption.split())
    base_file = Path(base_file).name  # never trust paths from the client
    if not caption:
        return base_file
    src = MEDIA_DIR / base_file
    if not src.is_file():
        raise FileNotFoundError(f"Image not found: {base_file}")

    img = Image.open(src).convert("RGB")
    W, H = img.size
    top = settings.image_caption_position.lower() == "top"
    margin = round(W * 0.055)
    size = max(18, round(W / 27))
    font = _font(size, caption)
    lines = _wrap(caption, font, W - 2 * margin, max_lines=3)
    tag = brand_tag()
    tag_font = _font(max(12, round(W / 56)), tag or "x")
    line_h = round(size * 1.25)
    bar_h = max(3, round(W * 0.005))
    block_h = bar_h + round(size * 0.45) + len(lines) * line_h + (round(tag_font.size * 1.9) if tag else 0)

    # soft dark gradient so the text stays readable on any photo
    grad_h = min(H, round(block_h + margin * 2.4))
    scrim = Image.new("RGBA", (W, grad_h))
    sd = ImageDraw.Draw(scrim)
    for y in range(grad_h):
        t = y / (grad_h - 1)
        t = 1 - t if top else t
        sd.line([(0, y), (W, y)], fill=(8, 10, 22, round(215 * (t ** 1.5))))
    canvas = img.convert("RGBA")
    y0 = 0 if top else H - grad_h
    canvas.alpha_composite(scrim, (0, y0))

    d = ImageDraw.Draw(canvas)
    y = (margin * 0.9) if top else (H - margin * 0.85 - block_h)
    y = round(y)
    accent = _hex(settings.image_accent)
    d.rounded_rectangle([margin, y, margin + round(W * 0.07), y + bar_h], radius=bar_h // 2, fill=(*accent, 255))
    y += bar_h + round(size * 0.45)
    for line in lines:
        d.text((margin + 2, y + 2), line, font=font, fill=(0, 0, 0, 120))  # soft shadow
        d.text((margin, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h
    if tag:
        d.text((margin, y + round(tag_font.size * 0.35)), tag.upper(), font=tag_font, fill=(255, 255, 255, 190))

    out = f"{Path(base_file).stem.split('_c')[0]}_c{uuid.uuid4().hex[:6]}.jpg"
    canvas.convert("RGB").save(MEDIA_DIR / out, "JPEG", quality=92)
    return out


def short_caption(title: str, limit: int = 70) -> str:
    """Fallback headline: the post topic, trimmed on a word boundary."""
    t = " ".join(title.split())
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(",:;-") + "…"
