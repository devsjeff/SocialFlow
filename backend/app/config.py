"""All configuration lives in the root .env file. Nothing brand-specific is hardcoded."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
MEDIA_DIR = BACKEND_DIR / "media"
PROMPTS_DIR = BACKEND_DIR / "prompts"


def _split(value: str, sep: str = ",") -> list[str]:
    return [p.strip() for p in value.split(sep) if p.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # --- app ---
    app_timezone: str = "UTC"
    dry_run: bool = True  # true = never call LinkedIn/Instagram, just simulate
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'scheduler.db').as_posix()}"
    public_base_url: str = "http://localhost:8000"  # Instagram needs a PUBLIC url to fetch images
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    scheduler_interval_seconds: int = 20

    # --- customer / brand profile (feeds every prompt) ---
    brand_name: str = "My Brand"
    brand_website: str = ""
    brand_industry: str = ""
    brand_description: str = ""
    brand_audience: str = ""
    brand_voice: str = "friendly, clear, confident"
    brand_language: str = "English"
    brand_keywords: str = ""  # comma separated SEO keywords
    brand_hashtags: str = ""  # comma separated default hashtags
    brand_cta: str = ""
    brand_facts: str = ""  # real facts the AI may use (packages, prices, process) - it must not invent others
    brand_avoid: str = ""  # claims / topics the AI must never make
    content_pillars: str = ""  # pipe or comma separated themes

    # --- posting rhythm ---
    posting_times: str = "09:30,18:00"  # local times in APP_TIMEZONE
    posting_days: str = "mon,wed,fri"
    default_platforms: str = "linkedin,instagram"
    auto_write: bool = True  # write missing text from the topic when publishing
    auto_image: bool = True  # generate a missing image when publishing

    # --- custom prompts: set to override the files in backend/prompts (use \n for newlines) ---
    post_prompt: str = ""
    ideas_prompt: str = ""

    # --- OpenRouter (text) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_text_models: str = "openrouter/free,google/gemma-4-31b-it:free"
    openrouter_referer: str = "http://localhost:3000"
    openrouter_app_title: str = "Post Scheduler"

    # --- images ---
    image_provider: str = "pollinations"  # pollinations (free, no key) | openrouter | none
    openrouter_image_model: str = "google/gemini-2.5-flash-image"  # paid but cheap; no free image models exist
    image_width: int = 1080
    image_height: int = 1080
    image_caption: bool = True  # draw a small AI-written caption on generated images
    image_caption_position: str = "bottom"  # bottom | top
    image_brand_tag: str = "auto"  # tiny label under the caption: "auto" = BRAND_NAME, empty = none
    image_accent: str = "#7c7ff7"  # colour of the small accent line above the caption
    image_style: str = "clean modern editorial illustration, soft lighting, no text, no logos"

    # --- "Connect" buttons (OAuth). Optional: you can still paste tokens manually below ---
    frontend_url: str = "http://localhost:3000"
    oauth_redirect_base: str = "http://localhost:8000"  # where LinkedIn/Meta send the user back (this backend)
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_scopes: str = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"

    # --- LinkedIn ---
    linkedin_access_token: str = ""
    linkedin_author_urn: str = ""  # urn:li:person:xxx or urn:li:organization:xxx (auto-detected for person if empty)
    linkedin_api_version: str = "202606"

    # --- Instagram (Graph API, Business/Creator account) ---
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    graph_api_version: str = "v23.0"

    # helpers -------------------------------------------------------------
    @property
    def keywords(self) -> list[str]:
        return _split(self.brand_keywords)

    @property
    def hashtags(self) -> list[str]:
        return [h.lstrip("#") for h in _split(self.brand_hashtags)]

    @property
    def pillars(self) -> list[str]:
        sep = "|" if "|" in self.content_pillars else ","
        return _split(self.content_pillars, sep)

    @property
    def times(self) -> list[str]:
        return _split(self.posting_times)

    @property
    def days(self) -> list[str]:
        return [d[:3].lower() for d in _split(self.posting_days)]

    @property
    def platforms(self) -> list[str]:
        return [p.lower() for p in _split(self.default_platforms)]

    @property
    def text_models(self) -> list[str]:
        return _split(self.openrouter_text_models)

    @property
    def origins(self) -> list[str]:
        return _split(self.cors_origins)

    def brand_profile(self) -> dict:
        return {
            "brand_name": self.brand_name,
            "brand_website": self.brand_website,
            "brand_industry": self.brand_industry,
            "brand_description": self.brand_description,
            "brand_audience": self.brand_audience,
            "brand_voice": self.brand_voice,
            "brand_language": self.brand_language,
            "brand_keywords": ", ".join(self.keywords),
            "brand_hashtags": " ".join("#" + h for h in self.hashtags),
            "brand_cta": self.brand_cta,
            "brand_facts": self.brand_facts,
            "brand_avoid": self.brand_avoid,
            "content_pillars": ", ".join(self.pillars),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
