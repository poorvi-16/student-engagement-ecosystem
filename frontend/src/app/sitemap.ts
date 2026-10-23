import type { MetadataRoute } from "next";
import { publicFetch, SITE_URL, type PostCard } from "@/lib/content";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const guides = (await publicFetch<PostCard[]>("/content?limit=100")) ?? [];
  return [
    { url: SITE_URL, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/guides`, changeFrequency: "daily", priority: 0.8 },
    ...guides.map((g) => ({ url: `${SITE_URL}/guides/${g.slug}`, lastModified: g.created_at, priority: 0.6 })),
  ];
}
