import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/content";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: ["/", "/guides"], disallow: ["/dashboard", "/admin", "/loan", "/card"] },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
