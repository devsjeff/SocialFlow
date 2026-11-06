"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { dayKey, fmtTime, isSameDay, monthGrid, WEEKDAYS } from "@/lib/dates";
import type { Post } from "@/lib/types";
import { useApp } from "@/components/AppProvider";
import PlanButton from "@/components/PlanButton";
import { PlatformIcon } from "@/components/ui";

const MAX_VISIBLE = 3;

export default function CalendarPage() {
  const { openComposer, version, reload, toast, config } = useApp();
  const [cursor, setCursor] = useState(() => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); });
  const [posts, setPosts] = useState<Post[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const grid = useMemo(() => monthGrid(cursor.getFullYear(), cursor.getMonth()), [cursor]);

  const load = useCallback(async () => {
    try {
      setPosts(await api.posts(grid[0].toISOString(), new Date(grid[41].getTime() + 86400000).toISOString()));
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }, [grid, toast]);
  useEffect(() => { load(); }, [load, version]);

  // while Auto-plan is still writing drafts, refresh every few seconds
  const anyWriting = posts.some((p) => p.writing);
  useEffect(() => {
    if (!anyWriting) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [anyWriting, load]);

  const byDay = useMemo(() => {
    const m = new Map<string, Post[]>();
    for (const p of posts) {
      if (!p.scheduled_at) continue;
      const k = dayKey(new Date(p.scheduled_at));
      m.set(k, [...(m.get(k) ?? []), p]);
    }
    return m;
  }, [posts]);

  const today = new Date();
  const shift = (n: number) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1));

  async function drop(day: Date, e: React.DragEvent) {
    e.preventDefault();
    setDragOver(null);
    const id = Number(e.dataTransfer.getData("text/post-id"));
    const post = posts.find((p) => p.id === id);
    if (!post?.scheduled_at) return;
    const old = new Date(post.scheduled_at);
    const next = new Date(day.getFullYear(), day.getMonth(), day.getDate(), old.getHours(), old.getMinutes());
    if (dayKey(next) === dayKey(old)) return;
    if (post.status === "scheduled" && next.getTime() < Date.now()) return toast("Can't move a scheduled post into the past", "err");
    setPosts((ps) => ps.map((p) => (p.id === id ? { ...p, scheduled_at: next.toISOString() } : p)));
    try {
      await api.update(id, { scheduled_at: next.toISOString() });
      toast(`Moved to ${next.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}`);
      reload();
    } catch (err) {
      toast((err as Error).message, "err");
      load();
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{cursor.toLocaleDateString([], { month: "long", year: "numeric" })}</h1>
          <p className="muted">
            Content calendar for <strong>{config?.brand.brand_name ?? "..."}</strong>. Click a day to add a post, drag posts to reschedule.
          </p>
        </div>
        <div className="row gap">
          <div className="seg compact">
            <button onClick={() => shift(-1)} aria-label="Previous month"><ChevronLeft size={16} /></button>
            <button onClick={() => setCursor(new Date(today.getFullYear(), today.getMonth(), 1))}>Today</button>
            <button onClick={() => shift(1)} aria-label="Next month"><ChevronRight size={16} /></button>
          </div>
          <PlanButton />
          <button className="btn primary" onClick={() => openComposer({ date: today })}><Plus size={15} /> New post</button>
        </div>
      </header>

      <div className="legend">
        {(["draft", "scheduled", "published", "failed"] as const).map((s) => (
          <span key={s}><i className={`dot st-${s}`} /> {s}</span>
        ))}
      </div>

      <div className="calendar">
        {WEEKDAYS.map((d) => <div key={d} className="cal-dow">{d}</div>)}
        {grid.map((day) => {
          const key = dayKey(day);
          const items = byDay.get(key) ?? [];
          const outside = day.getMonth() !== cursor.getMonth();
          const isPast = day < new Date(today.getFullYear(), today.getMonth(), today.getDate());
          const showAll = expanded === key;
          const visible = showAll ? items : items.slice(0, MAX_VISIBLE);
          return (
            <div
              key={key}
              className={`cal-cell ${outside ? "outside" : ""} ${isSameDay(day, today) ? "today" : ""} ${dragOver === key ? "drag" : ""}`}
              onClick={(e) => { if (e.target === e.currentTarget || (e.target as HTMLElement).dataset.add) openComposer({ date: day }); }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(key); }}
              onDragLeave={() => setDragOver((k) => (k === key ? null : k))}
              onDrop={(e) => drop(day, e)}
            >
              <div className="cal-num" onClick={() => openComposer({ date: day })} data-add="1">
                <span>{day.getDate()}</span>
                {!isPast && <button className="add" aria-label="Add post" data-add="1"><Plus size={13} data-add="1" /></button>}
              </div>
              {visible.map((p) => {
                const locked = p.status === "published" || p.status === "publishing";
                return (
                  <button
                    key={p.id}
                    className={`event st-${p.status} ${p.writing ? "writing" : ""}`}
                    draggable={!locked}
                    onDragStart={(e) => e.dataTransfer.setData("text/post-id", String(p.id))}
                    onClick={(e) => { e.stopPropagation(); openComposer({ post: p }); }}
                    title={p.title}
                  >
                    <span className="time">{fmtTime(p.scheduled_at)}</span>
                    <span className="icons">{p.platforms.map((pl) => <PlatformIcon key={pl} platform={pl} size={12} />)}</span>
                    {p.writing ? <span className="writing-dot" title="Being written" /> : p.status === "draft" && <span className="tag">draft</span>}
                    <span className="ttl">{p.title || "Untitled"}</span>
                  </button>
                );
              })}
              {items.length > MAX_VISIBLE && (
                <button className="more" onClick={(e) => { e.stopPropagation(); setExpanded(showAll ? null : key); }}>
                  {showAll ? "Show less" : `+${items.length - MAX_VISIBLE} more`}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
