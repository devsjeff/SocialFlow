"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CalendarCheck, CheckCircle2, Circle, FileEdit, Plus, RotateCw, Send, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative } from "@/lib/dates";
import type { Post, Stats } from "@/lib/types";
import { useApp } from "@/components/AppProvider";
import PlanButton from "@/components/PlanButton";
import { PlatformIcon, ScoreRing, StatusBadge } from "@/components/ui";

export default function Dashboard() {
  const { config, version, openComposer, reload, toast } = useApp();
  const [stats, setStats] = useState<Stats | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api.stats().then((s) => { setStats(s); setErr(""); }).catch((e) => setErr(e.message));
  }, []);
  useEffect(() => { load(); }, [load, version]);
  const writingNow = (stats?.writing ?? 0) > 0;
  useEffect(() => {
    const t = setInterval(load, writingNow ? 5000 : 30000);
    return () => clearInterval(t);
  }, [load, writingNow]);

  async function retry(p: Post) {
    try {
      const r = await api.publish(p.id);
      toast(r.status === "published" ? "Published" : `Still ${r.status}: see details`, r.status === "published" ? "ok" : "err");
      reload();
    } catch (e) { toast((e as Error).message, "err"); }
  }

  const c = stats?.counts;
  const maxAct = Math.max(1, ...(stats?.activity.map((a) => a.count) ?? [1]));
  const setup = [
    { ok: !!config?.ai.configured, label: "OpenRouter key for AI writing", hint: "Add OPENROUTER_API_KEY in .env (free)" },
    { ok: !!config?.integrations.linkedin, label: "LinkedIn connected", hint: "Add LINKEDIN_ACCESS_TOKEN" },
    { ok: !!config?.integrations.instagram, label: "Instagram connected", hint: "Add INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_USER_ID" },
  ];

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Hi, {config?.brand.brand_name ?? "there"} 👋</h1>
          <p className="muted">Here is what is happening with your LinkedIn and Instagram content.</p>
        </div>
        <div className="row gap">
          <PlanButton />
          <button className="btn primary" onClick={() => openComposer()}><Plus size={15} /> New post</button>
        </div>
      </header>

      {err && <div className="banner bad"><TriangleAlert size={16} /> {err}</div>}

      <section className="stat-grid">
        <Stat icon={<CalendarCheck size={18} />} tone="scheduled" label="Scheduled" value={c?.scheduled} />
        <Stat icon={<Send size={18} />} tone="published" label="Published" value={c?.published} />
        <Stat icon={<FileEdit size={18} />} tone="draft" label="Drafts" value={c?.draft} sub={stats?.empty_drafts ? `${stats.empty_drafts} need writing` : undefined} />
        <Stat icon={<TriangleAlert size={18} />} tone="failed" label="Needs attention" value={(c?.failed ?? 0) + (c?.partial ?? 0)} />
      </section>

      {stats && stats.attention.length > 0 && (
        <section className="card attention">
          <h3><TriangleAlert size={16} /> Needs attention</h3>
          {stats.attention.map((p) => (
            <div key={p.id} className="list-row">
              <div className="grow" onClick={() => openComposer({ post: p })} role="button">
                <strong>{p.title || "Untitled"}</strong>
                <small>{Object.entries(p.results).filter(([, r]) => r && !r.ok).map(([pl, r]) => `${pl}: ${r?.error}`).join(" | ")}</small>
              </div>
              <StatusBadge status={p.status} />
              <button className="btn small" onClick={() => retry(p)}><RotateCw size={13} /> Retry</button>
            </div>
          ))}
        </section>
      )}

      {stats && stats.drafts.length > 0 && (
        <section className="card" style={{ marginBottom: 16 }}>
          <div className="row between">
            <h3>Drafts <small>click one to edit, regenerate or post it now</small></h3>
            <Link href="/calendar" className="link">See on calendar <ArrowRight size={14} /></Link>
          </div>
          {stats.drafts.map((p) => {
            const written = !!(p.linkedin_text || p.instagram_caption);
            return (
              <div key={p.id} className="list-row clickable" onClick={() => openComposer({ post: p })}>
                <div className="when">
                  <strong>{p.scheduled_at ? fmtRelative(p.scheduled_at) : "No date"}</strong>
                  <small>{fmtDateTime(p.scheduled_at)}</small>
                </div>
                <div className="grow">
                  <strong>{p.title || "Untitled"}</strong>
                  <small>
                    {p.writing ? "Writing text and image..." : written ? (p.image_file ? "Text and image ready" : "Text ready, image will be created when posted") : "Not written yet, it will be written when you post"}
                  </small>
                </div>
                {p.writing && <span className="writing-dot" title="Being written" />}
                <div className="icons">{p.platforms.map((pl) => <PlatformIcon key={pl} platform={pl} size={18} />)}</div>
                {written && <ScoreRing score={p.seo.score} size={36} label="SEO score" />}
              </div>
            );
          })}
        </section>
      )}

      <div className="dash-grid">
        <section className="card">
          <div className="row between">
            <h3>Up next</h3>
            <Link href="/calendar" className="link">Open calendar <ArrowRight size={14} /></Link>
          </div>
          {!stats?.upcoming.length ? (
            <div className="empty">
              <p>Nothing scheduled yet.</p>
              <button className="btn" onClick={() => openComposer()}><Plus size={14} /> Create your first post</button>
            </div>
          ) : stats.upcoming.map((p) => (
            <div key={p.id} className="list-row clickable" onClick={() => openComposer({ post: p })}>
              <div className="when"><strong>{fmtRelative(p.scheduled_at!)}</strong><small>{fmtDateTime(p.scheduled_at)}</small></div>
              <div className="grow"><strong>{p.title || "Untitled"}</strong></div>
              <div className="icons">{p.platforms.map((pl) => <PlatformIcon key={pl} platform={pl} size={18} />)}</div>
              <ScoreRing score={p.seo.score} size={36} label="SEO score" />
            </div>
          ))}
        </section>

        <div className="stack">
          <section className="card">
            <h3>Average SEO score</h3>
            <div className="row gap center-v">
              <ScoreRing score={stats?.avg_seo ?? null} size={84} />
              <p className="muted small-text">
                {stats?.avg_seo == null ? "Write a post to see how search-friendly it is."
                  : stats.avg_seo >= 80 ? "Great. Your posts are well optimised."
                  : "Open a post and follow the checklist tips to push this higher."}
              </p>
            </div>
          </section>

          <section className="card">
            <h3>Next 14 days</h3>
            <div className="bars">
              {stats?.activity.map((a) => (
                <div key={a.date} className="bar-col" title={`${a.date}: ${a.count} post(s)`}>
                  <div className="bar" style={{ height: `${(a.count / maxAct) * 100}%`, opacity: a.count ? 1 : 0.15, minHeight: a.count ? 6 : 3 }} />
                  <small>{new Date(a.date + "T00:00").getDate()}</small>
                </div>
              ))}
            </div>
            <div className="split">
              <span><PlatformIcon platform="linkedin" size={16} /> {stats?.by_platform.linkedin ?? 0}</span>
              <span><PlatformIcon platform="instagram" size={16} /> {stats?.by_platform.instagram ?? 0}</span>
            </div>
          </section>

          <section className="card">
            <h3>Setup checklist</h3>
            {setup.map((s) => (
              <div key={s.label} className={`check-row ${s.ok ? "ok" : ""}`}>
                {s.ok ? <CheckCircle2 size={17} /> : <Circle size={17} />}
                <div><span>{s.label}</span>{!s.ok && <small>{s.hint}</small>}</div>
              </div>
            ))}
            <Link href="/settings" className="link">Brand & setup details <ArrowRight size={14} /></Link>
          </section>
        </div>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, tone, sub }: { icon: React.ReactNode; label: string; value?: number; tone: string; sub?: string }) {
  return (
    <div className="card stat">
      <div className={`stat-icon st-${tone}`}>{icon}</div>
      <div>
        <small>{label}</small>
        <strong>{value ?? "-"}</strong>
        {sub && <em>{sub}</em>}
      </div>
    </div>
  );
}
