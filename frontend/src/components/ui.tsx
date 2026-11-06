"use client";
import { useState } from "react";
import { X } from "lucide-react";
import type { Platform, Status } from "@/lib/types";

export function PlatformIcon({ platform, size = 18 }: { platform: Platform; size?: number }) {
  if (platform === "linkedin")
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" aria-label="LinkedIn" role="img">
        <rect width="24" height="24" rx="5" fill="#0a66c2" />
        <path d="M7.1 9.6h2.4V17H7.1zM8.3 6.2a1.4 1.4 0 110 2.8 1.4 1.4 0 010-2.8zM11.1 9.6h2.3v1c.4-.7 1.2-1.2 2.4-1.2 2.4 0 2.9 1.5 2.9 3.5V17h-2.4v-3.6c0-.9 0-2-1.2-2s-1.4.9-1.4 1.9V17h-2.4z" fill="#fff" />
      </svg>
    );
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Instagram" role="img">
      <defs>
        <linearGradient id="ig" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#feda75" />
          <stop offset=".35" stopColor="#fa7e1e" />
          <stop offset=".6" stopColor="#d62976" />
          <stop offset="1" stopColor="#4f5bd5" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill="url(#ig)" />
      <rect x="6" y="6" width="12" height="12" rx="3.6" fill="none" stroke="#fff" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="2.8" fill="none" stroke="#fff" strokeWidth="1.6" />
      <circle cx="15.6" cy="8.4" r=".9" fill="#fff" />
    </svg>
  );
}

const STATUS_LABEL: Record<Status, string> = {
  draft: "Draft", scheduled: "Scheduled", publishing: "Publishing", published: "Published", partial: "Partial", failed: "Failed",
};

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge st-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function ScoreRing({ score, size = 64, label }: { score: number | null; size?: number; label?: string }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const v = score ?? 0;
  const color = score === null ? "var(--muted)" : v >= 80 ? "var(--good)" : v >= 55 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="ring" style={{ width: size, height: size }} title={label}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="6" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * v) / 100} style={{ transition: "stroke-dashoffset .5s" }}
        />
      </svg>
      <span style={{ fontSize: size * 0.3 }}>{score === null ? "-" : v}</span>
    </div>
  );
}

export function Chips({
  values, onChange, placeholder, prefix = "",
}: { values: string[]; onChange: (v: string[]) => void; placeholder: string; prefix?: string }) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const parts = raw.split(/[,\n]/).map((s) => s.trim().replace(/^#/, "")).filter(Boolean);
    if (!parts.length) return;
    const next = [...values];
    for (const p of parts) if (!next.some((v) => v.toLowerCase() === p.toLowerCase())) next.push(p);
    onChange(next);
    setText("");
  };
  return (
    <div className="chips">
      {values.map((v) => (
        <span key={v} className="chip">
          {prefix}{v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}>
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(text); }
          else if (e.key === "Backspace" && !text && values.length) onChange(values.slice(0, -1));
        }}
        onBlur={() => add(text)}
      />
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden />;
}
