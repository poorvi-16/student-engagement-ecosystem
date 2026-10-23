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
              <Link href={`/guides/${g.slug}`} className="block h-full rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 dark:border-gray-800">
                <h2 className="font-semibold">{g.title}</h2>
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
