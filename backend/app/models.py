from datetime import datetime, timezone
from typing import Optional

from pydantic import NaiveDatetime
from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, Session, SQLModel, create_engine

from .config import settings

STATUSES = ("draft", "scheduled", "publishing", "published", "partial", "failed")


def utcnow() -> datetime:
    """Naive UTC datetime (SQLite has no tz support, so everything is stored as UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Post(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = ""  # topic / internal name
    notes: str = ""  # angle / reminders (not published)
    platforms: list = Field(default_factory=lambda: ["linkedin", "instagram"], sa_column=Column(JSON))
    linkedin_text: str = ""
    instagram_caption: str = ""
    hashtags: list = Field(default_factory=list, sa_column=Column(JSON))
    keywords: list = Field(default_factory=list, sa_column=Column(JSON))
    image_prompt: str = ""
    image_file: str = ""  # filename inside media/ OR an http(s) url
    alt_text: str = ""
    image_caption: str = ""  # small text drawn on the photo
    image_base: str = ""  # the clean image (without caption), so the caption can be edited later
    scheduled_at: Optional[NaiveDatetime] = Field(default=None, index=True)
    status: str = Field(default="draft", index=True)
    results: dict = Field(default_factory=dict, sa_column=Column(JSON))  # per-platform publish result
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class Connection(SQLModel, table=True):
    """OAuth-connected account. Tokens stay in the DB and are never sent to the browser."""
    platform: str = Field(primary_key=True)  # linkedin | instagram
    access_token: str = ""
    expires_at: Optional[NaiveDatetime] = None  # None = does not expire
    account_id: str = ""  # linkedin: urn:li:person:xxx | instagram: IG business user id
    account_name: str = ""
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


# columns added after the first release: added in place so existing databases keep working
_NEW_COLUMNS = ("image_caption", "image_base")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        have = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(post)")}
        for col in _NEW_COLUMNS:
            if col not in have:
                conn.exec_driver_sql(f"ALTER TABLE post ADD COLUMN {col} VARCHAR NOT NULL DEFAULT ''")


def get_session():
    with Session(engine) as session:
        yield session
