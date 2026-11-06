import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DRY_RUN"] = "true"
os.environ["BRAND_KEYWORDS"] = "social media marketing,content calendar"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["LINKEDIN_CLIENT_ID"] = "cid"
os.environ["LINKEDIN_CLIENT_SECRET"] = "csecret"
os.environ["META_APP_ID"] = ""
os.environ["LINKEDIN_ACCESS_TOKEN"] = ""
os.environ["FRONTEND_URL"] = "http://front.test"

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seo import score_platform  # noqa: E402


def test_seo_rewards_keyword_hook_and_hashtags():
    good = score_platform(
        "linkedin",
        "Social media marketing is simpler than you think.\n\nStart with one goal.\n\nPlan a content calendar.\n\nWhat do you think?",
        ["a", "b", "c"], [], True, "alt text",
    )
    bad = score_platform("linkedin", "hello", [], [], False, "")
    assert good["score"] > bad["score"]
    assert any(c["passed"] for c in good["checks"])


def test_full_flow_schedule_and_publish_dry_run():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"]
        cfg = client.get("/api/config").json()
        assert cfg["dry_run"] is True

        # AI is not configured -> template fallback still returns content
        gen = client.post("/api/ai/generate", json={"topic": "Content calendars"}).json()
        assert gen["source"] == "template" and gen["linkedin_text"]

        when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        post = client.post("/api/posts", json={
            "title": "Content calendars", "linkedin_text": gen["linkedin_text"],
            "instagram_caption": gen["instagram_caption"], "hashtags": ["#one", "two"],
            "scheduled_at": when, "status": "scheduled",
        }).json()
        assert post["status"] == "scheduled" and post["hashtags"] == ["one", "two"]
        assert post["scheduled_at"].endswith("Z")

        listed = client.get("/api/posts").json()
        assert len(listed) == 1

        done = client.post(f"/api/posts/{post['id']}/publish").json()
        assert done["status"] == "published"
        assert all(r["ok"] and r["simulated"] for r in done["results"].values())

        assert client.put(f"/api/posts/{post['id']}", json={"title": "x"}).status_code == 409
        stats = client.get("/api/stats").json()
        assert stats["counts"]["published"] == 1

        plan = client.post("/api/plan", json={"count": 3}).json()
        assert len(plan) == 3 and all(p["scheduled_at"] for p in plan)


def test_oauth_connect_flow(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from app import oauth
    from app.models import Connection, utcnow

    with TestClient(app) as client:
        cfg = client.get("/api/config").json()
        assert cfg["oauth"]["linkedin"]["ready"] is True
        assert cfg["oauth"]["instagram"]["ready"] is False and "META_APP_ID" in cfg["oauth"]["instagram"]["missing"]
        assert cfg["integrations"]["linkedin"] is False

        # not configured -> clear error, not a crash
        assert client.get("/api/oauth/instagram/start", follow_redirects=False).status_code == 400

        start = client.get("/api/oauth/linkedin/start", follow_redirects=False)
        assert start.status_code == 302
        url = urlparse(start.headers["location"])
        q = parse_qs(url.query)
        assert url.netloc == "www.linkedin.com" and q["client_id"] == ["cid"]
        assert "w_member_social" in q["scope"][0]
        assert q["redirect_uri"] == ["http://localhost:8000/api/oauth/linkedin/callback"]
        state = q["state"][0]

        # bad state is rejected and sent back to the frontend with an error
        bad = client.get("/api/oauth/linkedin/callback?code=x&state=nope", follow_redirects=False)
        assert bad.status_code == 302 and bad.headers["location"].startswith("http://front.test/settings?error=")

        async def fake_complete(platform, code):
            conn = Connection(platform="linkedin", access_token="tok", account_id="urn:li:person:abc",
                              account_name="Ada", expires_at=utcnow().replace(year=utcnow().year + 1))
            from sqlmodel import Session

            from app.models import engine
            with Session(engine) as s:
                s.merge(conn)
                s.commit()
            return conn

        monkeypatch.setattr(oauth, "complete", fake_complete)
        ok = client.get(f"/api/oauth/linkedin/callback?code=abc&state={state}", follow_redirects=False)
        assert ok.headers["location"] == "http://front.test/settings?connected=linkedin"

        # state is single-use
        replay = client.get(f"/api/oauth/linkedin/callback?code=abc&state={state}", follow_redirects=False)
        assert "error=" in replay.headers["location"]

        cfg = client.get("/api/config").json()
        assert cfg["integrations"]["linkedin"] is True
        assert cfg["accounts"]["linkedin"]["name"] == "Ada" and "tok" not in str(cfg)
        assert oauth.linkedin_creds() == ("tok", "urn:li:person:abc")

        assert client.delete("/api/oauth/linkedin").json()["ok"]
        assert client.get("/api/config").json()["integrations"]["linkedin"] is False
        assert client.get("/api/oauth/tiktok/start", follow_redirects=False).status_code == 404


def _fake_ai(monkeypatch, source="ai"):
    from app import ai

    async def fake_gen(topic, platforms, extra=""):
        return {"linkedin_text": "LI text", "instagram_caption": "IG text", "hashtags": ["a"], "keywords": ["k"],
                "image_prompt": "pic of x", "alt_text": "alt", "source": source, "warning": "no key"}

    async def fake_img(prompt):
        assert prompt == "pic of x"
        return "auto.jpg"

    monkeypatch.setattr(ai, "generate_post", fake_gen)
    monkeypatch.setattr(ai, "generate_image", fake_img)


def test_post_now_auto_writes_text_and_image(monkeypatch):
    _fake_ai(monkeypatch)
    with TestClient(app) as client:
        p = client.post("/api/posts", json={"title": "Topic only", "platforms": ["linkedin"]}).json()
        assert p["linkedin_text"] == "" and p["image_file"] == ""
        done = client.post(f"/api/posts/{p['id']}/publish").json()
        assert done["status"] == "published"
        assert done["linkedin_text"] == "LI text" and done["image_file"] == "auto.jpg" and done["alt_text"] == "alt"
        assert list(done["results"]) == ["linkedin"]  # only the chosen platform


def test_post_now_never_publishes_the_offline_template(monkeypatch):
    _fake_ai(monkeypatch, source="template")
    with TestClient(app) as client:
        p = client.post("/api/posts", json={"title": "Topic only", "platforms": ["linkedin"]}).json()
        done = client.post(f"/api/posts/{p['id']}/publish").json()
        assert done["status"] == "failed"
        assert "AI writing failed" in done["results"]["linkedin"]["error"]


def test_plan_with_platform_choice_and_background_write(monkeypatch):
    import time

    _fake_ai(monkeypatch)
    with TestClient(app) as client:
        made = client.post("/api/plan", json={"count": 2, "platforms": ["linkedin"], "write": True}).json()
        assert all(m["platforms"] == ["linkedin"] and m["status"] == "draft" for m in made)
        ids = {m["id"] for m in made}
        for _ in range(40):
            rows = [p for p in client.get("/api/posts").json() if p["id"] in ids]
            if all(r["linkedin_text"] and not r["writing"] for r in rows):
                break
            time.sleep(0.25)
        assert all(r["linkedin_text"] == "LI text" and r["image_file"] == "auto.jpg" for r in rows)
        stats = client.get("/api/stats").json()
        assert any(d["id"] in ids for d in stats["drafts"]) and stats["writing"] == 0
