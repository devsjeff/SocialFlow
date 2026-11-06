"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, LayoutDashboard, Plus, Settings, TriangleAlert } from "lucide-react";
import { useApp } from "./AppProvider";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/settings", label: "Brand & setup", icon: Settings },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { config, configError, openComposer } = useApp();
  const brand = config?.brand.brand_name ?? "Scheduler";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="avatar">{brand.slice(0, 1).toUpperCase()}</div>
          <div>
            <strong>{brand}</strong>
            <small>{config?.brand.brand_industry || "Post scheduler"}</small>
          </div>
        </div>
        <button className="btn primary block" onClick={() => openComposer()}>
          <Plus size={16} /> New post
        </button>
        <nav>
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={path === href ? "active" : ""}>
              <Icon size={17} /> {label}
            </Link>
          ))}
        </nav>
        <div className="side-foot">
          {config && (
            <span className={`pill ${config.dry_run ? "warn" : "good"}`}>
              <i /> {config.dry_run ? "Dry-run mode" : "Live posting"}
            </span>
          )}
          <small>Times shown in your browser timezone. Slots follow {config?.timezone ?? "UTC"}.</small>
        </div>
      </aside>
      <main className="main">
        {configError && (
          <div className="banner bad">
            <TriangleAlert size={16} />
            <div>
              <strong>Backend not reachable.</strong> {configError}
              <br />
              Start it with <code>uvicorn app.main:app --reload</code> inside <code>backend/</code>.
            </div>
          </div>
        )}
        {config?.dry_run && (
          <div className="banner warn">
            <TriangleAlert size={16} />
            <div>
              <strong>Dry-run is ON.</strong> Posts are simulated and nothing is sent to LinkedIn or Instagram. Set{" "}
              <code>DRY_RUN=false</code> in <code>.env</code> when your tokens are ready.
            </div>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
