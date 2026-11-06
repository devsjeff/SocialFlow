# Post Scheduler - LinkedIn + Instagram

A free, self-hosted content calendar. Write SEO-friendly posts with AI, see them on a calendar, and let the
Python backend publish them on time.

- **Frontend:** Next.js (dashboard, drag-and-drop calendar, post editor with live SEO score)
- **Backend:** FastAPI + SQLite, a built-in scheduler loop, no Redis/Celery needed
- **AI text:** OpenRouter free models (`openrouter/free` auto-picks one)
- **AI images:** Pollinations (free, no key) - or OpenRouter image models (paid, cheap)
- **Everything about the customer, prompts and tokens lives in `.env`**

## Run it (Windows)

Double-click `start.bat`. It creates `.env`, installs everything on the first run, starts both servers and opens
<http://localhost:3000>.

Manual way:

```bash
# terminal 1 - API
cd backend
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# terminal 2 - UI
cd frontend
npm install && npm run dev
```

It starts in **DRY_RUN=true** mode: scheduling, calendar and "publishing" all work, but nothing is sent to LinkedIn or
Instagram. Flip to `DRY_RUN=false` when your tokens are in.

## What you configure (`.env`)

| Block | Variables | What it does |
|---|---|---|
| Customer | `BRAND_NAME`, `BRAND_INDUSTRY`, `BRAND_DESCRIPTION`, `BRAND_AUDIENCE`, `BRAND_VOICE`, `BRAND_LANGUAGE`, `BRAND_CTA`, `CONTENT_PILLARS` | Fed into every AI prompt |
| SEO | `BRAND_KEYWORDS`, `BRAND_HASHTAGS` | AI must use them; the SEO checker scores against them |
| Rhythm | `APP_TIMEZONE`, `POSTING_DAYS`, `POSTING_TIMES` | Where Auto-plan puts posts, and the quick-pick slots in the editor |
| Prompts | `backend/prompts/post.md`, `ideas.md`, or `POST_PROMPT` / `IDEAS_PROMPT` in `.env` | Change the writing style, platform rules, or the whole niche |
| Text AI | `OPENROUTER_API_KEY`, `OPENROUTER_TEXT_MODELS` | Free key at <https://openrouter.ai/keys> |
| Images | `IMAGE_PROVIDER`, `IMAGE_STYLE`, `IMAGE_WIDTH/HEIGHT` | Style suffix added to every image prompt |
| LinkedIn | `LINKEDIN_ACCESS_TOKEN` (+ optional `LINKEDIN_AUTHOR_URN`) | Real posting |
| Instagram | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`, `PUBLIC_BASE_URL` | Real posting |

To reuse this for another customer, change the `BRAND_*` block (and optionally the prompt files) and restart the API.

## How it works

1. **Auto-plan** asks the AI for N topic ideas (from your pillars + keywords) and places them as drafts on your next
   free posting slots.
2. Open a draft, press **Write with AI**: you get a LinkedIn post, an Instagram caption, 3-5 hashtags, SEO keywords,
   an image prompt and alt text in one go. Press **Generate** for the image (or upload your own).
3. The **SEO panel** scores each platform live (keyword in the hook, hashtag count, length, CTA, scannability, image +
   alt text, character limit) and tells you what to fix.
   Press **Regenerate** to redo just that one post. **Post now** on a draft that has no text or image creates them
   first (`AUTO_WRITE` / `AUTO_IMAGE` in `.env`), so a planned topic can go out with one click. The offline template
   is never auto-published: if the AI fails, the post fails with the reason instead.
   Tick only **LinkedIn** (or only Instagram) per post; `DEFAULT_PLATFORMS` sets the default.
   **Captions on photos:** each generated image gets a small headline (written by the AI with the post, editable in
   *Caption on photo*) drawn at the bottom with your brand name under it. The clean photo is kept, so editing or
   clearing the caption never degrades the image. Control it with `IMAGE_CAPTION*` in `.env`.
4. **Schedule**. The backend checks every 20 seconds and publishes due posts. Failed platforms show the exact error and
   can be retried without re-posting the platform that already succeeded.

## Connect your accounts (one click)

Instead of copying tokens by hand, use the **Connect** buttons in *Brand & setup*. You still create the developer app
once (that is a LinkedIn/Meta requirement), but after that it is just a consent screen.

1. **LinkedIn:** at <https://developer.linkedin.com> create an app, add the products *Share on LinkedIn* and
   *Sign In with LinkedIn using OpenID Connect*, and under *Auth* add the redirect URL
   `http://localhost:8000/api/oauth/linkedin/callback`. Put the Client ID / Secret in `.env`
   (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`).
2. **Instagram:** at <https://developers.facebook.com> create an app with the Instagram content-publishing use case,
   add *Facebook Login* with the redirect URL `http://localhost:8000/api/oauth/instagram/callback`, and put the App ID / Secret in
   `.env` (`META_APP_ID`, `META_APP_SECRET`). Your Instagram account must be Business/Creator and linked to a Facebook Page.
3. Restart the API, open *Brand & setup*, press **Connect**, approve, and you are sent back with a green tick.

Tokens are stored in the local database and never sent to the browser. LinkedIn tokens last about 60 days (the page
shows the days left; press *Reconnect* before they expire). The Instagram Page token obtained this way does not expire.
A token pasted into `.env` still works as a fallback.

## Honest notes on the "free" parts

- **OpenRouter has no free image models** (checked against its model list). That is why images default to Pollinations,
  which is free and keyless. If you set `IMAGE_PROVIDER=openrouter`, it uses `OPENROUTER_IMAGE_MODEL` (cheap, but paid)
  and falls back to Pollinations on failure. Free text models are rate-limited, and the list changes, so
  `openrouter/free` is the safest default. Check <https://openrouter.ai/models?q=free>.
- **LinkedIn:** create an app at <https://developer.linkedin.com>, add the *Share on LinkedIn* product, and generate a
  token with `w_member_social` (+ `openid profile` so your author ID is auto-detected). Tokens last about 60 days.
  Posting as a company page needs `w_organization_social` and `LINKEDIN_AUTHOR_URN=urn:li:organization:...`.
- **Instagram:** needs a Business or Creator account linked to a Facebook Page, plus a Meta app with
  `instagram_content_publish`. Instagram *downloads* the image from a public URL, so for real posting expose the
  backend with a free tunnel (`cloudflared tunnel --url http://localhost:8000` or ngrok) and set `PUBLIC_BASE_URL`
  to that URL. Instagram does not allow text-only posts.
- The LinkedIn and Instagram publishers **and the Connect flows** are written against the official APIs but have **not
  been tested with live accounts** (the OAuth routes are covered by automated tests with the provider calls mocked).
  Meta in particular may ask you to add permissions or switch the app to Live mode. Do a first test with a private/test account after setting `DRY_RUN=false`.
- The scheduler runs inside the API process, so the backend must be running at the scheduled time. Late posts publish
  as soon as it starts again.

## Project layout

```
.env.example            all settings, documented
backend/app/            FastAPI app (main, ai, seo, publishers, service, models, config)
backend/prompts/        editable AI prompts
backend/tests/          pytest (python -m pytest)
frontend/src/app/       dashboard, calendar, settings pages
frontend/src/components editor drawer, calendar helpers, UI bits
```
