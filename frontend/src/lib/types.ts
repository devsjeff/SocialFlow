export type Platform = "linkedin" | "instagram";
export type Status = "draft" | "scheduled" | "publishing" | "published" | "partial" | "failed";

export interface SeoCheck { label: string; passed: boolean; tip: string }
export interface SeoPlatform { platform: Platform; score: number; chars: number; checks: SeoCheck[] }
export interface Seo { score: number; platforms: SeoPlatform[] }

export interface PublishResult { ok: boolean; id: string; url: string; error: string; simulated: boolean; at: string }

export interface Post {
  id: number;
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
  scheduled_at: string | null;
  status: Status;
  writing: boolean;
  results: Partial<Record<Platform, PublishResult>>;
  seo: Seo;
  created_at: string;
  updated_at: string;
}

export type PostInput = Partial<Pick<Post,
  "title" | "notes" | "platforms" | "linkedin_text" | "instagram_caption" | "hashtags" | "keywords" |
  "image_prompt" | "image_file" | "image_base" | "image_caption" | "alt_text" | "scheduled_at">> & { status?: "draft" | "scheduled" };

export interface Account {
  connected: boolean;
  expired: boolean;
  source: "oauth" | "env" | "";
  name: string;
  expires_at: string | null;
}

export interface Config {
  brand: Record<string, string>;
  keywords: string[];
  hashtags: string[];
  pillars: string[];
  timezone: string;
  posting_times: string[];
  posting_days: string[];
  default_platforms: Platform[];
  dry_run: boolean;
  auto_write: boolean;
  auto_image: boolean;
  image_caption: boolean;
  ai: { configured: boolean; models: string[]; image_provider: string; image_model: string };
  integrations: Record<Platform, boolean>;
  accounts: Record<Platform, Account>;
  oauth: Record<Platform, { ready: boolean; missing: string[]; redirect_uri: string }>;
  public_url_is_local: boolean;
}

export interface Stats {
  counts: Record<"draft" | "scheduled" | "published" | "partial" | "failed", number>;
  total: number;
  upcoming: Post[];
  attention: Post[];
  drafts: Post[];
  writing: number;
  empty_drafts: number;
  avg_seo: number | null;
  by_platform: Record<Platform, number>;
  activity: { date: string; count: number }[];
}

export interface Generated {
  linkedin_text: string;
  instagram_caption: string;
  hashtags: string[];
  keywords: string[];
  image_caption: string;
  image_prompt: string;
  alt_text: string;
  source: "ai" | "template";
  warning: string;
}
