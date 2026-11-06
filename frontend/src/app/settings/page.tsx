"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Link2, Unplug } from "lucide-react";
import { api } from "@/lib/api";
import type { Platform } from "@/lib/types";
import { useApp } from "@/components/AppProvider";
import { PlatformIcon } from "@/components/ui";

const NAMES: Record<Platform, string> = { linkedin: "LinkedIn", instagram: "Instagram" };
const MANUAL_ENV: Record<Platform, string> = {
  linkedin: "LINKEDIN_ACCESS_TOKEN",
  instagram: "INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_USER_ID",
};

function daysLeft(iso: string | null) {
  return iso ? Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000)) : null;
}

const FIELDS: [string, string, string][] = [
  ["brand_name", "Brand name", "BRAND_NAME"],
  ["brand_website", "Website", "BRAND_WEBSITE"],
  ["brand_industry", "Industry", "BRAND_INDUSTRY"],
  ["brand_description", "What you do", "BRAND_DESCRIPTION"],
  ["brand_audience", "Audience", "BRAND_AUDIENCE"],
  ["brand_voice", "Voice", "BRAND_VOICE"],
  ["brand_language", "Language", "BRAND_LANGUAGE"],
  ["brand_cta", "Call to action", "BRAND_CTA"],
  ["brand_facts", "Facts the AI may use", "BRAND_FACTS"],
  ["brand_avoid", "Never claim / never do", "BRAND_AVOID"],
  ["content_pillars", "Content pillars", "CONTENT_PILLARS"],
];

export default function Settings() {
  const { config, refreshConfig, toast } = useApp();
  const [busy, setBusy] = useState<Platform | null>(null);

  // the OAuth round-trip comes back as ?connected=... or ?error=...
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const ok = q.get("connected");
    const err = q.get("error");
    if (!ok && !err) return;
    if (ok) toast(`${NAMES[ok as Platform] ?? ok} connected`);
    if (err) toast(err, "err");
    window.history.replaceState(null, "", "/settings");
  }, [toast]);

  async function disconnect(p: Platform) {
    if (!window.confirm(`Disconnect ${NAMES[p]}? Scheduled posts for it will fail until you reconnect.`)) return;
    setBusy(p);
    try {
      await api.disconnect(p);
      toast(`${NAMES[p]} disconnected`);
      refreshConfig();
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(null);
    }
  }

  if (!config) return <div className="page"><p className="muted">Loading...</p></div>;
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Brand & setup</h1>
          <p className="muted">
            Everything here comes from <code>.env</code> in the project root. Edit it, restart the backend, and every prompt and
            SEO check uses the new values. Nothing is hardcoded.
          </p>
        </div>
      </header>

      <div className="two-col">
        <section className="card">
          <h3>Customer profile</h3>
          <dl className="defs">
            {FIELDS.map(([key, label, env]) => (
              <div key={key}>
                <dt>{label} <code>{env}</code></dt>
                <dd>{config.brand[key] || <em className="muted">not set</em>}</dd>
              </div>
            ))}
            <div>
              <dt>SEO keywords <code>BRAND_KEYWORDS</code></dt>
              <dd className="tags">{config.keywords.length ? config.keywords.map((k) => <span key={k} className="chip">{k}</span>) : <em className="muted">not set</em>}</dd>
            </div>
            <div>
              <dt>Default hashtags <code>BRAND_HASHTAGS</code></dt>
              <dd className="tags">{config.hashtags.map((k) => <span key={k} className="chip">#{k}</span>)}</dd>
            </div>
          </dl>
        </section>

        <div className="stack">
          <section className="card">
            <h3>Connections</h3>
            {(["linkedin", "instagram"] as Platform[]).map((p) => {
              const acc = config.accounts[p];
              const o = config.oauth[p];
              const left = daysLeft(acc.expires_at);
              return (
                <div key={p} className="conn col">
                  <div className="row gap">
                    <PlatformIcon platform={p} size={22} />
                    <div className="grow">
                      <strong>{NAMES[p]}</strong>
                      <small>
                        {acc.expired
                          ? "Token expired, please reconnect"
                          : acc.source === "oauth"
                            ? `Connected as ${acc.name}${left !== null ? ` · renew in ${left} days` : " · does not expire"}`
                            : acc.source === "env"
                              ? "Using the token from .env"
                              : "Not connected"}
                      </small>
                    </div>
                    {acc.connected ? <CheckCircle2 size={18} className="good-text" /> : <Circle size={18} className="muted" />}
                  </div>
                  <div className="row gap">
                    {o.ready ? (
                      <a className={`btn small ${acc.connected ? "" : "primary"}`} href={api.connectUrl(p)}>
                        <Link2 size={13} /> {acc.source === "oauth" || acc.expired ? "Reconnect" : `Connect ${NAMES[p]}`}
                      </a>
                    ) : (
                      <button className="btn small" disabled title={`Add ${o.missing.join(" and ")} to .env`}>
                        <Link2 size={13} /> Connect {NAMES[p]}
                      </button>
                    )}
                    {acc.source === "oauth" && (
                      <button className="btn small danger ghost" disabled={busy === p} onClick={() => disconnect(p)}>
                        <Unplug size={13} /> Disconnect
                      </button>
                    )}
                  </div>
                  {!o.ready && (
                    <p className="hint">
                      To enable this button, add <code>{o.missing.join(" and ")}</code> to <code>.env</code>, restart the API,
                      and register this redirect URL in your {p === "linkedin" ? "LinkedIn" : "Meta"} app:{" "}
                      <code>{o.redirect_uri}</code>. Or paste a token manually: <code>{MANUAL_ENV[p]}</code>.
                    </p>
                  )}
                </div>
              );
            })}
            <div className="conn">
              <span className="ai-badge">AI</span>
              <div className="grow">
                <strong>OpenRouter text</strong>
                <small>{config.ai.configured ? config.ai.models.join(" → ") : "Set OPENROUTER_API_KEY (free key)"}</small>
              </div>
              {config.ai.configured ? <CheckCircle2 size={18} className="good-text" /> : <Circle size={18} className="muted" />}
            </div>
            <div className="conn">
              <span className="ai-badge">IMG</span>
              <div className="grow"><strong>Images</strong><small>{config.ai.image_provider} · {config.ai.image_model}</small></div>
              <CheckCircle2 size={18} className="good-text" />
            </div>
            {config.public_url_is_local && (
              <p className="note">
                <code>PUBLIC_BASE_URL</code> is localhost. Instagram can only fetch images from a public URL, so use a free tunnel
                (cloudflared / ngrok) before posting to Instagram for real.
              </p>
            )}
          </section>

          <section className="card">
            <h3>Rhythm & mode</h3>
            <dl className="defs">
              <div><dt>Timezone <code>APP_TIMEZONE</code></dt><dd>{config.timezone}</dd></div>
              <div><dt>Posting days <code>POSTING_DAYS</code></dt><dd>{config.posting_days.join(", ")}</dd></div>
              <div><dt>Posting times <code>POSTING_TIMES</code></dt><dd>{config.posting_times.join(", ")}</dd></div>
              <div><dt>Mode <code>DRY_RUN</code></dt><dd>{config.dry_run ? "Dry-run (simulated)" : "Live posting"}</dd></div>
            </dl>
          </section>

          <section className="card">
            <h3>Change the AI prompts</h3>
            <p className="muted small-text">
              Edit <code>backend/prompts/post.md</code> and <code>ideas.md</code>, or paste a one-line override into{" "}
              <code>POST_PROMPT</code> / <code>IDEAS_PROMPT</code> in <code>.env</code>. Placeholders like{" "}
              <code>{"{{brand_name}}"}</code>, <code>{"{{brand_keywords}}"}</code> and <code>{"{{topic}}"}</code> are filled in
              automatically, so you can retarget the whole tool to a new customer or niche in minutes.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
