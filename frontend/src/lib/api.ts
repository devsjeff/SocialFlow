import type { Config, Generated, Platform, Post, PostInput, Seo, Stats } from "./types";

export interface ImageResult { image_base: string; image_file: string; image_url: string }

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new Error(`Can't reach the backend at ${API}. Is it running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  config: () => req<Config>("/api/config"),
  connectUrl: (platform: Platform) => `${API}/api/oauth/${platform}/start`,
  disconnect: (platform: Platform) => req<{ ok: boolean }>(`/api/oauth/${platform}`, { method: "DELETE" }),
  stats: () => req<Stats>("/api/stats"),
  posts: (start?: string, end?: string) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return req<Post[]>(`/api/posts?${q}`);
  },
  get: (id: number) => req<Post>(`/api/posts/${id}`),
  create: (p: PostInput) => req<Post>("/api/posts", json("POST", p)),
  update: (id: number, p: PostInput) => req<Post>(`/api/posts/${id}`, json("PUT", p)),
  remove: (id: number) => req<{ ok: boolean }>(`/api/posts/${id}`, { method: "DELETE" }),
  publish: (id: number) => req<Post>(`/api/posts/${id}/publish`, { method: "POST" }),
  generate: (topic: string, platforms: string[], extra = "") =>
    req<Generated>("/api/ai/generate", json("POST", { topic, platforms, extra })),
  image: (prompt: string, caption = "") =>
    req<ImageResult>("/api/ai/image", json("POST", { prompt, caption })),
  caption: (image_base: string, caption: string) =>
    req<ImageResult>("/api/image/caption", json("POST", { image_base, caption })),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<ImageResult>("/api/upload", { method: "POST", body: fd });
  },
  plan: (count: number, platforms: Platform[], write: boolean) =>
    req<Post[]>("/api/plan", json("POST", { count, platforms, write })),
  seo: (p: PostInput) => req<Seo>("/api/seo/score", json("POST", p)),
};

export const mediaUrl = (url: string) => (!url ? "" : url.startsWith("http") ? url : `${API}${url}`);
