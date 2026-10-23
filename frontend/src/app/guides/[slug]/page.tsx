import type { Metadata } from "next";
import Link from "next/link";
import { Markdown } from "@/components/Markdown";
import { RefCapture } from "@/components/RefCapture";
import { ViewPing } from "@/components/ViewPing";
import { publicFetch, tagLabel, type Post } from "@/lib/content";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const post = await publicFetch<Post>(`/content/${slug}?count=false`);
  if (!post) return { title: "Guide · PathPilot" };
  return {
    title: `${post.title} · PathPilot`,
    description: post.summary,
    openGraph: { title: post.title, description: post.summary, type: "article" },
  };
}

export default async function GuidePage({ params }: Props) {
  const { slug } = await params;
  const post = await publicFetch<Post>(`/content/${slug}?count=false`);

  if (!post) {
    return (
      <main className="mx-auto max-w-md space-y-4 p-8 text-center">
        <p className="text-gray-600 dark:text-gray-400">This guide isn&apos;t available right now.</p>
        <Link href="/guides" className="text-indigo-600 hover:underline">
          Browse all guides →
        </Link>
      </main>
    );
  }

  const signup = `/login?utm_source=guide&utm_medium=seo&utm_campaign=${encodeURIComponent(slug)}`;
  return (
    <main className="mx-auto max-w-2xl space-y-6 p-4 sm:p-8">
      <RefCapture />
      <ViewPing slug={slug} />
      <nav className="text-sm">
        <Link href="/guides" className="text-indigo-600 hover:underline">
          ← All guides
        </Link>
      </nav>
      <article className="space-y-4">
        <h1 className="text-3xl font-bold leading-tight">{post.title}</h1>
        <p className="text-gray-600 dark:text-gray-400">{post.summary}</p>
        <div className="flex flex-wrap gap-2">
          {post.tags.map((t) => (
            <span key={t} className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs capitalize dark:bg-gray-900">
              {tagLabel(t)}
            </span>
          ))}
        </div>
        <Markdown text={post.body} />
      </article>

      {post.sources.length > 0 && (
        <p className="text-xs text-gray-500">
          Sources:{" "}
          {post.sources.map((s) => (
            <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="underline">
              {s.title}
            </a>
          ))}
          . Last reviewed {post.sources[0].reviewed}. Rules and fees change, so check the official source before you act.
          {post.ai ? " Drafted with AI from our reviewed guides." : ""}
        </p>
      )}

      <section className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-700 p-6 text-white">
        <h2 className="text-xl font-semibold">Plan your own journey with PathPilot</h2>
        <p className="mt-1 text-sm opacity-90">
          Match universities to your profile, see your admit odds and total cost, then check education-loan options. Free to start.
        </p>
        <Link href={signup} className="mt-4 inline-block rounded-lg bg-white px-4 py-2 text-sm font-semibold text-indigo-700">
          Get started free
        </Link>
      </section>

      {post.related.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">More guides</h2>
          <ul className="space-y-2">
            {post.related.map((r) => (
              <li key={r.slug}>
                <Link href={`/guides/${r.slug}`} className="text-indigo-600 hover:underline">
                  {r.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
