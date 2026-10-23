"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";

/** Counts the view from the browser (the server render doesn't), and logs it for signed-in students. */
export function ViewPing({ slug }: { slug: string }) {
  useEffect(() => {
    api(`/content/${slug}`).catch(() => {});
  }, [slug]);
  return null;
}
