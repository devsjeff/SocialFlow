"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Config, Post } from "@/lib/types";
import Composer from "./Composer";

export interface ComposerOpts { post?: Post; date?: Date; title?: string }
interface Ctx {
  config: Config | null;
  configError: string | null;
  version: number; // bumps whenever data changes, pages refetch on it
  reload: () => void;
  refreshConfig: () => void;
  openComposer: (o?: ComposerOpts) => void;
  toast: (msg: string, kind?: "ok" | "err") => void;
}
const AppCtx = createContext<Ctx | null>(null);
export const useApp = () => {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
};

export default function AppProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [composer, setComposer] = useState<ComposerOpts | null>(null);
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: "ok" | "err" }[]>([]);

  const refreshConfig = useCallback(() => {
    api.config().then((c) => { setConfig(c); setConfigError(null); }).catch((e) => setConfigError(e.message));
  }, []);
  useEffect(() => { refreshConfig(); }, [refreshConfig]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const toast = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "err" ? 7000 : 3500);
  }, []);
  const openComposer = useCallback((o: ComposerOpts = {}) => setComposer(o), []);

  const value = useMemo(
    () => ({ config, configError, version, reload, refreshConfig, openComposer, toast }),
    [config, configError, version, reload, refreshConfig, openComposer, toast],
  );

  return (
    <AppCtx.Provider value={value}>
      {children}
      {composer && (
        <Composer
          key={composer.post?.id ?? `new-${composer.date?.getTime() ?? 0}-${composer.title ?? ""}`}
          opts={composer}
          onClose={() => setComposer(null)}
        />
      )}
      <div className="toasts" role="status">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>
        ))}
      </div>
    </AppCtx.Provider>
  );
}
