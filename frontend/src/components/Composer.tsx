"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check, CircleAlert, ExternalLink, ImagePlus, Lightbulb, Send, Sparkles, Trash2, Upload, Wand2, X,
} from "lucide-react";
import { api, mediaUrl } from "@/lib/api";
import { atTime, dayKey, fmtDateTime, fromLocalInput, toLocalInput, WEEKDAYS } from "@/lib/dates";
import type { Platform, Post, Seo } from "@/lib/types";
import { type ComposerOpts, useApp } from "./AppProvider";
import { Chips, PlatformIcon, ScoreRing, Spinner, StatusBadge } from "./ui";

const LIMIT: Record<Platform, number> = { linkedin: 3000, instagram: 2200 };
const HOOK: Record<Platform, number> = { linkedin: 210, instagram: 125 };
const NAME: Record<Platform, string> = { linkedin: "LinkedIn", instagram: "Instagram" };

interface Form {
  title: string;
  notes: string;
  platforms: Platform[];
  linkedin_text: string;
  instagram_caption: string;
  hashtags: string[];
  keywords: string[];
  image_prompt: string;
  image_file: string;
  image_url: string;
  image_base: string;
  image_caption: string;
  alt_text: string;
  when: string;
}

export default function Composer({ opts, onClose }: { opts: ComposerOpts; onClose: () => void }) {
  const { config, reload, toast } = useApp();
  const post = opts.post;
  const readOnly = post?.status === "published" || post?.status === "publishing";

  const [form, setForm] = useState<Form>(() => ({
    title: post?.title ?? opts.title ?? "",
    notes: post?.notes ?? "",
    platforms: post?.platforms ?? config?.default_platforms ?? ["linkedin", "instagram"],
    linkedin_text: post?.linkedin_text ?? "",
    instagram_caption: post?.instagram_caption ?? "",
    hashtags: post?.hashtags ?? config?.hashtags.slice(0, 5) ?? [],
    keywords: post?.keywords ?? [],
    image_prompt: post?.image_prompt ?? "",
    image_file: post?.image_file ?? "",
    image_url: post?.image_url ?? "",
    image_base: post?.image_base ?? "",
    image_caption: post?.image_caption ?? "",
    alt_text: post?.alt_text ?? "",
    when: post?.scheduled_at
      ? toLocalInput(post.scheduled_at)
      : opts.date
        ? toLocalInput(atTime(opts.date, config?.posting_times[0] ?? "09:30").toISOString())
        : "",
  }));
  const [tab, setTab] = useState<Platform>(form.platforms[0] ?? "linkedin");
  const [busy, setBusy] = useState<"" | "gen" | "img" | "save" | "publish" | "upload">("");
  const [extra, setExtra] = useState("");
  const [seo, setSeo] = useState<Seo | null>(post?.seo ?? null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [writing, setWriting] = useState(!!post?.writing);

  // redraw the small caption on the clean image whenever the caption text changes
  const rendered = useRef(`${post?.image_base ?? ""}|${post?.image_caption ?? ""}`);
  useEffect(() => {
    if (readOnly || !form.image_base) return;
    const key = `${form.image_base}|${form.image_caption}`;
    if (key === rendered.current) return;
    const t = setTimeout(async () => {
      try {
        const r = await api.caption(form.image_base, form.image_caption);
        rendered.current = key;
        setForm((f) => (f.image_base === form.image_base ? { ...f, image_file: r.image_file, image_url: r.image_url } : f));
      } catch (e) {
        toast((e as Error).message, "err");
      }
    }, 700);
    return () => clearTimeout(t);
  }, [form.image_base, form.image_caption, readOnly, toast]);

  // a draft that Auto-plan is still writing in the background: pull in the result when it is ready
  useEffect(() => {
    if (!post || !writing) return;
    const t = setInterval(async () => {
      try {
        const fresh = await api.get(post.id);
        if (fresh.writing) return;
        setForm((f) => ({
          ...f,
          linkedin_text: f.linkedin_text || fresh.linkedin_text,
          instagram_caption: f.instagram_caption || fresh.instagram_caption,
          image_file: f.image_file || fresh.image_file,
          image_url: f.image_url || fresh.image_url,
          image_prompt: f.image_prompt || fresh.image_prompt,
          alt_text: f.alt_text || fresh.alt_text,
          keywords: f.keywords.length ? f.keywords : fresh.keywords,
        }));
        setWriting(false);
        reload();
      } catch {}
    }, 4000);
    return () => clearInterval(t);
  }, [writing, post, reload]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const activeTab: Platform = form.platforms.includes(tab) ? tab : form.platforms[0] ?? "linkedin";

  // live SEO score (debounced)
  useEffect(() => {
    const t = setTimeout(() => {
      api
        .seo({
          platforms: form.platforms, linkedin_text: form.linkedin_text, instagram_caption: form.instagram_caption,
          hashtags: form.hashtags, keywords: form.keywords, image_file: form.image_file, alt_text: form.alt_text,
        })
        .then(setSeo)
        .catch(() => {});
    }, 450);
    return () => clearTimeout(t);
  }, [form.platforms, form.linkedin_text, form.instagram_caption, form.hashtags, form.keywords, form.image_file, form.alt_text]);

  // next posting slots in browser time, from POSTING_DAYS / POSTING_TIMES
  const slots = useMemo(() => {
    const out: Date[] = [];
    const days = config?.posting_days ?? [];
    const now = new Date();
    for (let i = 0; i < 21 && out.length < 4; i++) {
      const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
      const name = WEEKDAYS[(day.getDay() + 6) % 7].toLowerCase();
      if (days.length && !days.includes(name)) continue;
      for (const t of config?.posting_times ?? ["09:30"]) {
        const d = atTime(day, t);
        if (d > now && out.length < 4) out.push(d);
      }
    }
    return out;
  }, [config]);

  const toggle = (p: Platform) => {
    if (readOnly) return;
    const next = form.platforms.includes(p) ? form.platforms.filter((x) => x !== p) : [...form.platforms, p];
    if (next.length) { set("platforms", next); setTab(next.includes(tab) ? tab : next[0]); }
  };

  async function generate() {
    if (form.title.trim().length < 2) return toast("Type a topic first, e.g. \"3 mistakes in Instagram reels\"", "err");
    if (hasText && !window.confirm("Replace the current text with a fresh AI version?")) return;
    setBusy("gen");
    try {
      const g = await api.generate(form.title.trim(), form.platforms, extra);
      setForm((f) => ({
        ...f,
        linkedin_text: g.linkedin_text || f.linkedin_text,
        instagram_caption: g.instagram_caption || f.instagram_caption,
        hashtags: g.hashtags.length ? g.hashtags : f.hashtags,
        keywords: g.keywords.length ? g.keywords : f.keywords,
        image_prompt: g.image_prompt || f.image_prompt,
        image_caption: g.image_caption || f.image_caption,
        alt_text: g.alt_text || f.alt_text,
      }));
      // a regenerated text deserves a matching picture: drop the old one so it is recreated
      if (form.image_file && g.source === "ai" && g.image_prompt) {
        setForm((f) => ({ ...f, image_file: "", image_url: "", image_base: "" }));
        rendered.current = "";
      }
      if (g.source === "template") toast(`Used a basic template (${g.warning || "AI unavailable"})`, "err");
      else toast("Draft written. Review and tweak it.");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy("");
    }
  }

  async function makeImage() {
    const prompt = form.image_prompt.trim() || form.title.trim();
    if (prompt.length < 3) return toast("Add an image prompt or a topic first", "err");
    setBusy("img");
    try {
      const caption = form.image_caption || (config?.image_caption ? form.title.trim() : "");
      const r = await api.image(prompt, caption);
      rendered.current = `${r.image_base}|${caption}`;
      setForm((f) => ({ ...f, image_file: r.image_file, image_url: r.image_url, image_base: r.image_base, image_caption: caption, image_prompt: prompt }));
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy("");
    }
  }

  async function onUpload(file?: File) {
    if (!file) return;
    setBusy("upload");
    try {
      const r = await api.upload(file);
      rendered.current = `${r.image_base}|`;
      setForm((f) => ({ ...f, image_file: r.image_file, image_url: r.image_url, image_base: r.image_base }));
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy("");
    }
  }

  const payload = (status: "draft" | "scheduled") => ({
    title: form.title.trim(),
    notes: form.notes,
    platforms: form.platforms,
    linkedin_text: form.linkedin_text,
    instagram_caption: form.instagram_caption,
    hashtags: form.hashtags,
    keywords: form.keywords,
    image_prompt: form.image_prompt,
    image_file: form.image_file,
    image_base: form.image_base,
    image_caption: form.image_caption,
    alt_text: form.alt_text,
    scheduled_at: fromLocalInput(form.when),
    status,
  });

  const hasText = !!(form.linkedin_text.trim() || form.instagram_caption.trim());
  const canAutoWrite = !!config?.auto_write && form.title.trim().length >= 2;

  function validateForSend(): string | null {
    for (const p of form.platforms) {
      const txt = p === "linkedin" ? form.linkedin_text : form.instagram_caption;
      if (!txt.trim() && !canAutoWrite) return `${NAME[p]} text is empty. Write it, or type a topic and it will be written for you.`;
    }
    if (form.platforms.includes("instagram") && !form.image_file && !config?.auto_image) return "Instagram needs an image";
    return null;
  }

  async function save(status: "draft" | "scheduled") {
    if (status === "scheduled") {
      const err = validateForSend() || (!form.when ? "Pick a date and time" : null);
      if (err) return toast(err, "err");
    }
    setBusy("save");
    try {
      if (post) await api.update(post.id, payload(status));
      else await api.create(payload(status));
      toast(status === "scheduled" ? `Scheduled for ${fmtDateTime(fromLocalInput(form.when))}` : "Saved as draft");
      reload();
      onClose();
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy("");
    }
  }

  async function publishNow() {
    const err = validateForSend();
    if (err) return toast(err, "err");
    if (!config?.dry_run && !window.confirm("Publish this post to the selected platforms right now?")) return;
    setBusy("publish");
    if ((!hasText && canAutoWrite) || (!form.image_file && config?.auto_image))
      toast("Creating the missing " + [!hasText && canAutoWrite ? "text" : "", !form.image_file && config?.auto_image ? "image" : ""].filter(Boolean).join(" and ") + " first. This can take a minute...");
    try {
      const saved = post ? await api.update(post.id, payload("draft")) : await api.create(payload("draft"));
      const done = await api.publish(saved.id);
      const failed = Object.entries(done.results).filter(([, r]) => r && !r.ok);
      if (failed.length) toast(failed.map(([p, r]) => `${NAME[p as Platform]}: ${r?.error}`).join(" | "), "err");
      else toast(config?.dry_run ? "Dry-run: publish simulated" : "Published!");
      reload();
      onClose();
    } catch (e) {
      toast((e as Error).message, "err");
      reload();
    } finally {
      setBusy("");
    }
  }

  async function remove(p: Post) {
    if (!window.confirm("Delete this post?")) return;
    try {
      await api.remove(p.id);
      toast("Deleted");
      reload();
      onClose();
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }

  const text = activeTab === "linkedin" ? form.linkedin_text : form.instagram_caption;
  const textKey = activeTab === "linkedin" ? "linkedin_text" : "instagram_caption";
  const tagString = form.hashtags.map((h) => "#" + h).join(" ");
  const totalChars = text.length + (tagString ? tagString.length + 2 : 0);
  const seoActive = seo?.platforms.find((p) => p.platform === activeTab);
  const ready = !busy;

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-label="Post editor">
        <header className="drawer-head">
          <div>
            <h2>{post ? "Edit post" : "New post"}</h2>
            {post && <StatusBadge status={post.status} />}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="drawer-body">
          <div className="col-main">
            <label className="field">
              <span>Topic</span>
              <div className="row">
                <input
                  value={form.title} disabled={readOnly}
                  placeholder="e.g. 3 mistakes that kill your Instagram reach"
                  onChange={(e) => set("title", e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !readOnly && generate()}
                />
                <button className="btn accent" disabled={!ready || readOnly} onClick={generate}>
                  {busy === "gen" ? <Spinner /> : <Sparkles size={16} />} {hasText ? "Regenerate" : "Write with AI"}
                </button>
              </div>
            </label>
            <label className="field">
              <span>Extra instructions <em>(optional)</em></span>
              <input value={extra} disabled={readOnly} placeholder="e.g. mention our Diwali offer, keep it under 800 characters"
                onChange={(e) => setExtra(e.target.value)} />
            </label>
            {writing && (
              <div className="note"><span className="writing-dot" /> This draft is being written in the background. The text and image will appear here in a moment.</div>
            )}
            {form.notes && <div className="note"><Lightbulb size={14} /> {form.notes}</div>}

            <div className="field">
              <span>Platforms</span>
              <div className="row gap">
                {(["linkedin", "instagram"] as Platform[]).map((p) => (
                  <button key={p} type="button" disabled={readOnly}
                    className={`toggle ${form.platforms.includes(p) ? "on" : ""}`} onClick={() => toggle(p)}>
                    <PlatformIcon platform={p} size={18} /> {NAME[p]}
                    {form.platforms.includes(p) && <Check size={14} />}
                    {config && !config.integrations[p] && !config.dry_run && <small>not connected</small>}
                  </button>
                ))}
              </div>
            </div>

            <div className="tabs">
              {form.platforms.map((p) => (
                <button key={p} className={activeTab === p ? "active" : ""} onClick={() => setTab(p)}>
                  <PlatformIcon platform={p} size={16} /> {NAME[p]}
                  {seo && <b className="mini-score">{seo.platforms.find((x) => x.platform === p)?.score}</b>}
                </button>
              ))}
            </div>
            <textarea
              className="editor" rows={13} disabled={readOnly} value={text}
              placeholder={activeTab === "linkedin" ? "Your LinkedIn post..." : "Your Instagram caption..."}
              onChange={(e) => set(textKey, e.target.value)}
            />
            <div className="meta-row">
              <span className={totalChars > LIMIT[activeTab] ? "bad-text" : ""}>{totalChars} / {LIMIT[activeTab]} characters (with hashtags)</span>
              {text && (
                <span className="hook" title="What people see before 'see more'">
                  <b>Hook:</b> {text.slice(0, HOOK[activeTab])}{text.length > HOOK[activeTab] ? "…" : ""}
                </span>
              )}
            </div>

            <div className="grid2">
              <div className="field">
                <span>Hashtags <em>3-5 works best</em></span>
                <Chips values={form.hashtags} onChange={(v) => set("hashtags", v)} placeholder="add hashtag + Enter" prefix="#" />
              </div>
              <div className="field">
                <span>SEO keywords <em>for this post</em></span>
                <Chips values={form.keywords} onChange={(v) => set("keywords", v)} placeholder="add keyword + Enter" />
              </div>
            </div>
          </div>

          <div className="col-side">
            <section className="card flat">
              <h3>Image</h3>
              {form.image_url ? (
                <div className="img-wrap">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={mediaUrl(form.image_url)} alt={form.alt_text || "Post image"} />
                  {!readOnly && (
                    <button className="icon-btn float" aria-label="Remove image"
                      onClick={() => { rendered.current = ""; setForm((f) => ({ ...f, image_file: "", image_url: "", image_base: "" })); }}><X size={14} /></button>
                  )}
                </div>
              ) : (
                <div className="img-empty">
                  <ImagePlus size={26} />
                  <span>No image yet</span>
                  {config?.auto_image && <small>One is created automatically when you post</small>}
                </div>
              )}
              <textarea rows={2} disabled={readOnly} value={form.image_prompt}
                placeholder="Image prompt (AI fills this for you)" onChange={(e) => set("image_prompt", e.target.value)} />
              <div className="row gap">
                <button className="btn" disabled={!ready || readOnly} onClick={makeImage}>
                  {busy === "img" ? <Spinner /> : <Wand2 size={15} />} {form.image_url ? "Regenerate" : "Generate"}
                </button>
                <button className="btn" disabled={!ready || readOnly} onClick={() => fileRef.current?.click()}>
                  {busy === "upload" ? <Spinner /> : <Upload size={15} />} Upload
                </button>
                <input ref={fileRef} type="file" hidden accept="image/png,image/jpeg"
                  onChange={(e) => { onUpload(e.target.files?.[0]); e.target.value = ""; }} />
              </div>
              <label className="field">
                <span>Caption on photo <em>small headline, empty = none</em></span>
                <input
                  disabled={readOnly} value={form.image_caption} maxLength={90}
                  placeholder={config?.image_caption ? "Written automatically with the post" : "e.g. Get found on Google Maps"}
                  onChange={(e) => {
                    const v = e.target.value;
                    // an image that has no clean original yet (older post): its current file becomes the original
                    setForm((f) => ({ ...f, image_caption: v, image_base: f.image_base || (f.image_file && !f.image_file.startsWith("http") ? f.image_file : "") }));
                  }}
                />
              </label>
              <input disabled={readOnly} value={form.alt_text} placeholder="Alt text (describe the image + a keyword)"
                onChange={(e) => set("alt_text", e.target.value)} />
            </section>

            <section className="card flat">
              <div className="row between">
                <h3>SEO score</h3>
                <ScoreRing score={seo?.score ?? null} size={52} />
              </div>
              {seoActive && (
                <ul className="checks">
                  {seoActive.checks.map((c) => (
                    <li key={c.label} className={c.passed ? "ok" : "no"}>
                      {c.passed ? <Check size={14} /> : <CircleAlert size={14} />}
                      <div>{c.label}{!c.passed && <small>{c.tip}</small>}</div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card flat">
              <h3>Schedule</h3>
              <input type="datetime-local" disabled={readOnly} value={form.when} onChange={(e) => set("when", e.target.value)} />
              <div className="row wrap gap">
                {slots.map((d) => (
                  <button key={d.getTime()} className="slot" disabled={readOnly}
                    onClick={() => set("when", toLocalInput(d.toISOString()))}>
                    {dayKey(d) === dayKey(new Date()) ? "Today" : d.toLocaleDateString([], { weekday: "short", day: "numeric" })}{" "}
                    {d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                  </button>
                ))}
              </div>
            </section>

            {post && Object.keys(post.results).length > 0 && (
              <section className="card flat">
                <h3>Publish results</h3>
                <ul className="results">
                  {Object.entries(post.results).map(([p, r]) => r && (
                    <li key={p} className={r.ok ? "ok" : "no"}>
                      <PlatformIcon platform={p as Platform} size={16} />
                      <div>
                        {r.ok ? (r.simulated ? "Simulated (dry-run)" : "Published") : "Failed"}
                        {r.error && <small>{r.error}</small>}
                      </div>
                      {r.url && <a href={r.url} target="_blank" rel="noreferrer" aria-label="Open post"><ExternalLink size={14} /></a>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>

        {!readOnly && (
          <footer className="drawer-foot">
            {post ? (
              <button className="btn danger ghost" onClick={() => remove(post)} disabled={!ready}><Trash2 size={15} /> Delete</button>
            ) : <span />}
            <div className="row gap">
              <button className="btn" disabled={!ready} onClick={() => save("draft")}>Save draft</button>
              <button className="btn" disabled={!ready} onClick={publishNow}>
                {busy === "publish" ? <Spinner /> : <Send size={15} />} Post now
              </button>
              <button className="btn primary" disabled={!ready} onClick={() => save("scheduled")}>
                {busy === "save" ? <Spinner /> : null} {post?.status === "failed" || post?.status === "partial" ? "Reschedule / retry" : "Schedule"}
              </button>
            </div>
          </footer>
        )}
      </aside>
    </div>
  );
}
