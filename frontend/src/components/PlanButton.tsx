"use client";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useApp } from "./AppProvider";
import type { Platform } from "@/lib/types";
import { PlatformIcon, Spinner } from "./ui";

/** Asks the AI for topic ideas and drops them as drafts on your next posting slots. */
export default function PlanButton({ className = "btn" }: { className?: string }) {
  const { reload, toast, config } = useApp();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(7);
  const [busy, setBusy] = useState(false);
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [write, setWrite] = useState(true);
  const chosen: Platform[] = platforms.length ? platforms : (config?.default_platforms ?? ["linkedin"]);

  const toggle = (p: Platform) => {
    const next = chosen.includes(p) ? chosen.filter((x) => x !== p) : [...chosen, p];
    if (next.length) setPlatforms(next);
  };

  async function run() {
    setBusy(true);
    try {
      const made = await api.plan(count, chosen, write);
      toast(write
        ? `Planned ${made.length} drafts. Text and images are being written in the background - click any draft to edit, regenerate or post it.`
        : `Planned ${made.length} drafts. Click one to write it, or just press Post now and it writes itself.`);
      reload();
      setOpen(false);
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className={className} onClick={() => setOpen(true)}><Sparkles size={15} /> Auto-plan</button>
      {open && (
        <div className="overlay center" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="modal">
            <h3>Auto-plan your calendar</h3>
            <p className="muted">
              The AI proposes post ideas based on your brand, keywords and content pillars, and places them on your next free
              slots ({config?.posting_days.join(", ")} at {config?.posting_times.join(" & ")}). They land as drafts, nothing is posted.
            </p>
            <div className="seg">
              {[7, 14, 30].map((n) => (
                <button key={n} className={count === n ? "active" : ""} onClick={() => setCount(n)}>{n} posts</button>
              ))}
            </div>
            <div className="field">
              <span>Post on</span>
              <div className="row gap">
                {(["linkedin", "instagram"] as Platform[]).map((p) => (
                  <button key={p} type="button" className={`toggle ${chosen.includes(p) ? "on" : ""}`} onClick={() => toggle(p)}>
                    <PlatformIcon platform={p} size={18} /> {p === "linkedin" ? "LinkedIn" : "Instagram"}
                  </button>
                ))}
              </div>
            </div>
            <label className="check-line">
              <input type="checkbox" checked={write} onChange={(e) => setWrite(e.target.checked)} />
              <span>Also write the text and create the image for each draft now <small>(background, about a minute per post on free models)</small></span>
            </label>
            {!config?.ai.configured && (
              <p className="note">No <code>OPENROUTER_API_KEY</code> yet, so basic placeholder topics will be used.</p>
            )}
            <div className="row gap end">
              <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
              <button className="btn primary" disabled={busy} onClick={run}>
                {busy ? <Spinner /> : <Sparkles size={15} />} Plan {count} posts
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
