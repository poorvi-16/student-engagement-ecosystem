"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PostCard } from "@/lib/content";
import { tagLabel } from "@/lib/content";
import { useMe } from "@/lib/useMe";

type Feed = { posts: PostCard[]; interests: string[] };
type Filter = "all" | PostCard["kind"];

const KIND = { guide: { icon: "📖", label: "Guide" }, reel: { icon: "🎬", label: "Reel script" }, linkedin: { icon: "💼", label: "LinkedIn post" } };

function ShortPost({ p }: { p: PostCard }) {
  const [copied, setCopied] = useState(false);
  return (
    <article className="space-y-2 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
      <p className="text-xs font-medium text-gray-500">
        {KIND[p.kind].icon} {KIND[p.kind].label} {p.why ? `· ${p.why}` : ""}
      </p>
      <h2 className="font-semibold">{p.title.replace(/^(Reel|LinkedIn): /, "")}</h2>
      <p className="whitespace-pre-line text-sm text-gray-700 dark:text-gray-300">{p.body}</p>
      <button
        onClick={() => {
          navigator.clipboard?.writeText(p.body ?? "");
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="text-sm text-indigo-600 hover:underline"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
    </article>
  );
}

export default function DiscoverPage() {
  const { me, loading } = useMe();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    if (!me) return;
    api<Feed>("/content/feed?limit=30")
      .then(setFeed)
      .catch((e) => setError(String(e.message ?? e)));
  }, [me]);

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  const posts = (feed?.posts ?? []).filter((p) => filter === "all" || p.kind === filter);

  return (
    <main className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-indigo-600 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="text-2xl font-bold">Discover</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Guides picked for your interests and stage. Written by our content agent from reviewed sources; always check official sites for fees and dates.
        </p>
        {feed && feed.interests.length > 0 && (
          <p className="text-xs capitalize text-gray-500">Your interests: {feed.interests.map(tagLabel).join(" · ")}</p>
        )}
      </header>

      <div className="flex gap-2 text-sm">
        {(["all", "guide", "reel", "linkedin"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 ${filter === f ? "bg-indigo-600 text-white" : "border border-gray-300 dark:border-gray-700"}`}
          >
            {f === "all" ? "All" : KIND[f].label + "s"}
          </button>
        ))}
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
      {!feed && !error && <p className="text-gray-500">Loading your feed…</p>}
      {feed && posts.length === 0 && <p className="text-gray-500">Nothing here yet. New content is published every day.</p>}

      <div className="space-y-4">
        {posts.map((p) =>
          p.kind === "guide" ? (
            <Link
              key={p.slug}
              href={`/guides/${p.slug}`}
              className="block rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 dark:border-gray-800"
            >
              <p className="text-xs font-medium text-gray-500">
                {KIND.guide.icon} Guide {p.why ? `· ${p.why}` : ""}
              </p>
              <h2 className="mt-1 font-semibold">{p.title}</h2>
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{p.summary}</p>
              <p className="mt-2 text-xs capitalize text-gray-500">{p.tags.map(tagLabel).join(" · ")}</p>
            </Link>
          ) : (
            <ShortPost key={p.slug} p={p} />
          ),
        )}
      </div>
    </main>
  );
}
