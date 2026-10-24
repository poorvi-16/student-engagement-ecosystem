import type { Metadata } from "next";
import Link from "next/link";
import { RefCapture } from "@/components/RefCapture";
import { publicFetch, tagLabel, type PostCard } from "@/lib/content";

export const metadata: Metadata = {
  title: "Study guides for Indian students · PathPilot",
  description: "Visas, tests, costs, scholarships and education loans explained simply, from our reviewed knowledge base.",
};

export default async function GuidesPage() {
  const guides = (await publicFetch<PostCard[]>("/content?limit=60")) ?? [];
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4 sm:p-8">
      <RefCapture />
      <header className="space-y-1">
        <Link href="/" className="text-sm text-indigo-600 hover:underline">
          ← PathPilot
        </Link>
        <h1 className="text-3xl font-bold">Study guides</h1>
        <p className="text-gray-600 dark:text-gray-400">Visas, tests, costs, scholarships and education loans for Indian students.</p>
      </header>
      {guides.length === 0 ? (
        <p className="text-gray-500">Guides are on their way. Check back soon.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {guides.map((g) => (
            <li key={g.slug}>
              <Link href={`/guides/${g.slug}`} className="lift block h-full rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
                <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">{g.aspect.label}</span>
                <h2 className="mt-2 font-semibold">{g.title}</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{g.summary}</p>
                <p className="mt-2 text-xs capitalize text-gray-500">{g.tags.map(tagLabel).join(" · ")}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
