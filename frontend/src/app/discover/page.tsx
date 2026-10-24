"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { PostCard } from "@/lib/content";
import { tagLabel } from "@/lib/content";
import { useMe } from "@/lib/useMe";

type Aspect = { id: string; label: string };
type Feed = { posts: PostCard[]; interests: string[]; aspects: Aspect[] };

const ASPECT_STYLE: Record<string, { icon: string; chip: string }> = {
  visa: { icon: "🛂", chip: "bg-sky-50 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300" },
  money: { icon: "💰", chip: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300" },
  apply: { icon: "📝", chip: "bg-violet-50 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300" },
  careers: { icon: "💼", chip: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300" },
  life: { icon: "🏡", chip: "bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300" },
  plan: { icon: "🧭", chip: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300" },
  countries: { icon: "🌍", chip: "bg-teal-50 text-teal-700 dark:bg-teal-950/60 dark:text-teal-300" },
};
const KIND = { guide: "Guide", reel: "Reel script", linkedin: "LinkedIn post" } as const;

function Sources({ post }: { post: PostCard }) {
  if (!post.sources.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-gray-500">Read the full source:</span>
      {post.sources.slice(0, 4).map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-full border border-[var(--line)] px-2.5 py-0.5 text-indigo-700 hover:border-indigo-400 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-indigo-950/50"
        >
          {s.title} ↗
        </a>
      ))}
    </div>
  );
}

function Badge({ post }: { post: PostCard }) {
  const st = ASPECT_STYLE[post.aspect.id] ?? ASPECT_STYLE.plan;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${st.chip}`}>
      <span aria-hidden>{st.icon}</span> {post.aspect.label}
    </span>
  );
}

function ShortPost({ p }: { p: PostCard }) {
  const [copied, setCopied] = useState(false);
  return (
    <article className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge post={p} />
        <span className="text-xs text-gray-500">{p.kind === "reel" ? "🎬" : "💼"} {KIND[p.kind]}</span>
      </div>
      <h2 className="mt-2 font-semibold">{p.title.replace(/^(Reel|LinkedIn): /, "")}</h2>
      <p className="mt-2 whitespace-pre-line rounded-xl bg-[var(--muted)] p-3 text-sm text-gray-700 dark:text-gray-300">{p.body}</p>
      <div className="mt-2 flex items-center justify-between">
        <Sources post={p} />
        <button
          onClick={() => {
            navigator.clipboard?.writeText(p.body ?? "");
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="shrink-0 text-sm text-indigo-600 hover:underline"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </article>
  );
}

function GuideCard({ p, featured = false }: { p: PostCard; featured?: boolean }) {
  return (
    <article className={`lift flex flex-col rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 ${featured ? "sm:col-span-2" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge post={p} />
        {p.why && <span className="text-xs text-gray-500">{p.why}</span>}
      </div>
      <Link href={`/guides/${p.slug}`} className="mt-2 block">
        <h2 className={`font-semibold leading-snug hover:text-indigo-600 ${featured ? "text-xl" : ""}`}>{p.title}</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{p.summary}</p>
      </Link>
      <p className="mt-2 text-xs capitalize text-gray-500">{p.tags.map(tagLabel).join(" · ")}</p>
      <div className="mt-auto pt-3">
        <Link href={`/guides/${p.slug}`} className="text-sm font-medium text-indigo-600 hover:underline">
          Read the guide →
        </Link>
        <Sources post={p} />
      </div>
    </article>
  );
}

export default function DiscoverPage() {
  const { me, loading } = useMe();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState("");
  const [aspect, setAspect] = useState("all");
  const [kind, setKind] = useState<"all" | "guide" | "short">("all");

  useEffect(() => {
    if (!me) return;
    api<Feed>("/content/feed?limit=50")
      .then(setFeed)
      .catch((e) => setError(String(e.message ?? e)));
  }, [me]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    feed?.posts.forEach((p) => (c[p.aspect.id] = (c[p.aspect.id] ?? 0) + 1));
    return c;
  }, [feed]);

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  const posts = (feed?.posts ?? []).filter((p) => (aspect === "all" || p.aspect.id === aspect) && (kind === "all" || (kind === "guide") === (p.kind === "guide")));
  const guides = posts.filter((p) => p.kind === "guide");
  const shorts = posts.filter((p) => p.kind !== "guide");

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-4 sm:p-8">
      <header className="gradient-brand rounded-3xl p-6 text-white shadow-lg shadow-indigo-500/20 sm:p-8">
        <h1 className="text-2xl font-bold sm:text-3xl">Discover</h1>
        <p className="mt-1 max-w-2xl text-indigo-100">
          Guides and articles on every side of the journey: visas, money, tests, careers and life abroad. Each one links to the official pages so you can read the whole
          thing.
        </p>
        {feed && feed.interests.length > 0 && <p className="mt-3 text-xs capitalize text-indigo-200">Picked for: {feed.interests.slice(0, 5).map(tagLabel).join(" · ")}</p>}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setAspect("all")}
          className={`rounded-full px-3.5 py-1.5 text-sm ${aspect === "all" ? "bg-indigo-600 text-white shadow-sm" : "border border-[var(--line)] hover:border-indigo-400"}`}
        >
          All ({feed?.posts.length ?? 0})
        </button>
        {feed?.aspects
          .filter((a) => counts[a.id])
          .map((a) => (
            <button
              key={a.id}
              onClick={() => setAspect(a.id)}
              className={`rounded-full px-3.5 py-1.5 text-sm ${aspect === a.id ? "bg-indigo-600 text-white shadow-sm" : "border border-[var(--line)] hover:border-indigo-400"}`}
            >
              {ASPECT_STYLE[a.id]?.icon} {a.label} ({counts[a.id]})
            </button>
          ))}
        <span className="ml-auto flex gap-1 text-xs">
          {(["all", "guide", "short"] as const).map((k) => (
            <button key={k} onClick={() => setKind(k)} className={`rounded-md px-2 py-1 ${kind === k ? "bg-[var(--muted)] font-semibold" : "text-gray-500"}`}>
              {k === "all" ? "Everything" : k === "guide" ? "Guides" : "Quick reads"}
            </button>
          ))}
        </span>
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
      {!feed && !error && <p className="text-gray-500">Loading your feed…</p>}
      {feed && posts.length === 0 && <p className="text-gray-500">Nothing here yet. New content is published every day.</p>}

      {guides.length > 0 && (
        <section className="grid gap-4 sm:grid-cols-2">
          {guides.map((p, i) => (
            <GuideCard key={p.slug} p={p} featured={i === 0 && aspect === "all" && kind !== "short"} />
          ))}
        </section>
      )}

      {shorts.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Quick reads</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {shorts.map((p) => (
              <ShortPost key={p.slug} p={p} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
