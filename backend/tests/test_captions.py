from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from app import ai, captions
from app.main import app


def _photo(path, size=(1080, 1080)):
    Image.new("RGB", size, (60, 120, 90)).save(path, "JPEG")


def test_caption_overlay_and_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(captions, "MEDIA_DIR", tmp_path)
    _photo(tmp_path / "base.jpg")

    out = captions.render("base.jpg", "Next.js SEO website in 14 working days")
    assert out != "base.jpg" and (tmp_path / out).is_file()
    a, b = Image.open(tmp_path / "base.jpg"), Image.open(tmp_path / out)
    assert a.size == b.size
    bottom = (0, int(a.height * 0.7), a.width, a.height)
    top = (0, 0, a.width, int(a.height * 0.3))
    assert ImageChops.difference(a.crop(bottom), b.crop(bottom)).getbbox() is not None  # drawn at the bottom
    assert ImageChops.difference(a.crop(top), b.crop(top)).getbbox() is None  # rest of the photo untouched
    assert captions.render("base.jpg", "   ") == "base.jpg"  # empty caption = clean image
    assert captions.short_caption("word " * 40).endswith("…")

    with TestClient(app) as client:
        ok = client.post("/api/image/caption", json={"image_base": "base.jpg", "caption": "Hello"}).json()
        assert ok["image_base"] == "base.jpg" and ok["image_file"].startswith("base_c")
        assert ok["image_url"] == "/media/" + ok["image_file"]
        clean = client.post("/api/image/caption", json={"image_base": "base.jpg", "caption": ""}).json()
        assert clean["image_file"] == "base.jpg"
        assert client.post("/api/image/caption", json={"image_base": "nope.jpg", "caption": "x"}).status_code == 404
        # a path from the client is reduced to a bare file name (no escaping the media folder)
        assert client.post("/api/image/caption", json={"image_base": "../../.env", "caption": "x"}).status_code == 404


def test_post_now_draws_the_auto_caption(monkeypatch, tmp_path):
    monkeypatch.setattr(captions, "MEDIA_DIR", tmp_path)
    _photo(tmp_path / "auto.jpg")

    async def fake_gen(topic, platforms, extra=""):
        return {"linkedin_text": "LI text", "instagram_caption": "IG text", "hashtags": ["a"], "keywords": ["k"],
                "image_caption": "Short headline", "image_prompt": "pic", "alt_text": "alt", "source": "ai", "warning": ""}

    async def fake_img(prompt):
        return "auto.jpg"

    monkeypatch.setattr(ai, "generate_post", fake_gen)
    monkeypatch.setattr(ai, "generate_image", fake_img)
    with TestClient(app) as client:
        p = client.post("/api/posts", json={"title": "Topic only", "platforms": ["linkedin"]}).json()
        done = client.post(f"/api/posts/{p['id']}/publish").json()
        assert done["status"] == "published"
        assert done["image_base"] == "auto.jpg" and done["image_caption"] == "Short headline"
        assert done["image_file"].startswith("auto_c") and (tmp_path / done["image_file"]).is_file()

        # IMAGE_CAPTION=false stops the automatic caption, but a caption you typed is still drawn
        monkeypatch.setattr(captions.settings, "image_caption", False)
        p2 = client.post("/api/posts", json={"title": "Second", "platforms": ["linkedin"], "image_caption": "Mine"}).json()
        d2 = client.post(f"/api/posts/{p2['id']}/publish").json()
        assert d2["image_caption"] == "Mine" and d2["image_file"].startswith("auto_c")
        p3 = client.post("/api/posts", json={"title": "Third", "platforms": ["linkedin"]}).json()
        d3 = client.post(f"/api/posts/{p3['id']}/publish").json()
        assert d3["image_file"] == "auto.jpg" and d3["image_caption"] == ""  # clean photo, nothing recorded


def test_old_database_gets_caption_columns(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    from app import models

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE post (id INTEGER PRIMARY KEY, title VARCHAR NOT NULL DEFAULT '')")
        c.exec_driver_sql("INSERT INTO post (id, title) VALUES (1, 'kept')")
    monkeypatch.setattr(models, "engine", eng)
    models.init_db()
    models.init_db()  # idempotent
    with eng.begin() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(post)")}
        assert {"image_caption", "image_base"} <= cols
        assert c.exec_driver_sql("SELECT title, image_caption FROM post").fetchone() == ("kept", "")
