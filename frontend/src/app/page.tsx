import Link from "next/link";
import { RefCapture } from "@/components/RefCapture";
import { publicFetch, tagLabel, type PostCard } from "@/lib/content";

const STEPS = [
  { icon: "🎯", title: "Know your odds", text: "Two minutes of questions, then AI-matched universities with your admit chances and real total cost." },
  { icon: "🗓️", title: "Plan every step", text: "A dated plan for tests, SOPs, deadlines, visa and funding, with a coach for each." },
  { icon: "🛂", title: "Practise and polish", text: "Get your SOP scored and rehearse a visa interview with an AI officer." },
  { icon: "💰", title: "Fund it", text: "Compare education-loan options, plan your EMIs and let the copilot fill the application." },
];

const FEATURES = [
  ["🧭", "Career Navigator", "Ambitious, Target and Safe programs with payback time"],
  ["🧑‍🏫", "AI Mentor", "Answers with sources, plus live cost and loan tools"],
  ["📚", "Discover", "Guides on visas, money, careers and student life"],
  ["✍️", "SOP reviewer", "Rubric score, fixes and a stronger opening"],
  ["📄", "Loan copilot", "Reads your documents and fills the form"],
  ["🏆", "XP and streaks", "Levels, badges and invites that keep you moving"],
];

export default async function Home() {
  const guides = ((await publicFetch<PostCard[]>("/content?limit=6")) ?? []).slice(0, 3);
  return (
    <main className="overflow-x-hidden">
      <RefCapture />

      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <span className="flex items-center gap-2 text-lg font-bold">
          <span className="gradient-brand flex h-9 w-9 items-center justify-center rounded-xl text-white">✈</span> PathPilot
        </span>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/guides" className="hidden text-gray-600 hover:text-indigo-600 sm:inline dark:text-gray-300">
            Guides
          </Link>
          <Link href="/login" className="rounded-full border border-indigo-300 px-4 py-1.5 font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950">
            Sign in
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-4xl px-4 pb-14 pt-10 text-center sm:px-6 sm:pt-16">
        <p className="mx-auto mb-5 w-fit rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300">
          ✨ Your AI copilot for studying abroad or in India
        </p>
        <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-6xl">
          From &ldquo;where should I study?&rdquo; to a <span className="gradient-text">funded loan application</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-gray-600 dark:text-gray-400">
          Find universities that fit, see your admit odds and true cost, prepare for the visa and plan how to pay, all in one place.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/login" className="gradient-brand rounded-full px-6 py-3 font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:opacity-95">
            Get started, it&apos;s free
          </Link>
          <Link href="/guides" className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-6 py-3 font-semibold hover:border-indigo-400">
            Read the guides
          </Link>
        </div>
        <ul className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-gray-500">
          <li>✓ No credit-score impact</li>
          <li>✓ Sources on every answer</li>
          <li>✓ Delete your data anytime</li>
        </ul>
      </section>

      <section className="mx-auto max-w-6xl px-4 sm:px-6">
        <h2 className="mb-6 text-center text-2xl font-bold">How PathPilot works</h2>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">{s.icon}</span>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wider text-indigo-600">Step {i + 1}</p>
              <h3 className="mt-0.5 font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto mt-14 max-w-6xl px-4 sm:px-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([icon, title, text]) => (
            <div key={title} className="flex items-start gap-3 rounded-2xl bg-[var(--muted)] p-4">
              <span className="text-2xl">{icon}</span>
              <div>
                <p className="font-semibold">{title}</p>
                <p className="text-sm text-gray-600 dark:text-gray-400">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {guides.length > 0 && (
        <section className="mx-auto mt-14 max-w-6xl px-4 sm:px-6">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-2xl font-bold">Fresh guides</h2>
            <Link href="/guides" className="text-sm font-medium text-indigo-600 hover:underline">
              All guides →
            </Link>
          </div>
          <ul className="grid gap-4 md:grid-cols-3">
            {guides.map((g) => (
              <li key={g.slug}>
                <Link href={`/guides/${g.slug}`} className="lift block h-full rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
                  <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">{g.aspect.label}</span>
                  <h3 className="mt-3 font-semibold leading-snug">{g.title}</h3>
                  <p className="mt-1 line-clamp-3 text-sm text-gray-600 dark:text-gray-400">{g.summary}</p>
                  <p className="mt-3 text-xs capitalize text-gray-500">{g.tags.slice(0, 3).map(tagLabel).join(" · ")}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mx-auto mt-14 max-w-4xl px-4 sm:px-6">
        <div className="gradient-brand rounded-3xl p-8 text-center text-white shadow-xl shadow-indigo-500/20 sm:p-12">
          <h2 className="text-2xl font-bold sm:text-3xl">Ready to see where you stand?</h2>
          <p className="mx-auto mt-2 max-w-lg text-indigo-100">Take the 2-minute quiz and get your profile strength, matched universities and funding estimate.</p>
          <Link href="/login" className="mt-6 inline-block rounded-full bg-white px-6 py-3 font-semibold text-indigo-700 transition hover:bg-indigo-50">
            Start free
          </Link>
        </div>
      </section>
    </main>
  );
}
