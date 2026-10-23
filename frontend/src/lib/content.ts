import { API_URL } from "@/lib/api";

export type PostCard = {
  slug: string;
  kind: "guide" | "reel" | "linkedin";
  title: string;
  summary: string;
  tags: string[];
  views: number;
  created_at: string;
  why: string | null;
  body: string | null;
};

export type Post = PostCard & {
  body: string;
  sources: { title: string; url: string; reviewed: string }[];
  ai: boolean;
  related: PostCard[];
};

/** Server-side fetch of public content, revalidated every 10 minutes. Returns null when the API is asleep or down. */
export async function publicFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 600 }, signal: AbortSignal.timeout(8000) });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://student-engagement-ecosystem.vercel.app";

export function tagLabel(tag: string) {
  return tag.split(":")[1]?.replace(/_/g, " ") ?? tag;
}
