import Link from "next/link";
import { RefCapture } from "@/components/RefCapture";
import { publicFetch, type PostCard } from "@/lib/content";

export default async function Home() {
  const guides = ((await publicFetch<PostCard[]>("/content?limit=3")) ?? []).slice(0, 3);
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 p-6 text-center">
      <RefCapture />
      <h1 className="text-4xl font-bold sm:text-5xl">PathPilot</h1>
      <p className="max-w-md text-gray-600 dark:text-gray-400">
        Your AI copilot for higher studies — find the right university, plan your applications, and fund your future.
      </p>
      <Link href="/login" className="rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700">
        Get started — it&apos;s free
      </Link>
      {guides.length > 0 && (
        <section className="mt-6 w-full max-w-2xl space-y-3 text-left">
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold">Fresh guides</h2>
            <Link href="/guides" className="text-sm text-indigo-600 hover:underline">
              All guides →
            </Link>
          </div>
          <ul className="grid gap-3 sm:grid-cols-3">
            {guides.map((g) => (
              <li key={g.slug}>
                <Link href={`/guides/${g.slug}`} className="block h-full rounded-xl border border-gray-200 p-4 text-sm transition hover:border-indigo-400 dark:border-gray-800">
                  <span className="font-medium">{g.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
