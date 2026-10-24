"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Match = {
  course_id: number;
  university: string;
  country: string;
  city: string;
  tier: number;
  qs_rank: number | null;
  program: string;
  duration_months: number;
  total_cost_lakhs: number;
  tuition_lakhs: number;
  living_lakhs: number;
  salary_lakhs: number;
  payback_years: number | null;
  funding_gap_lakhs: number;
  chance: number;
  bucket: "ambitious" | "target" | "safe";
  deadline_month: number;
  stem: boolean;
  why: string;
  watch_out: string;
};

type NavResult = {
  summary: string;
  ai: boolean;
  notice: string | null;
  matches: Match[];
  shortlist: number[];
  disclaimer: string;
};

const BUCKETS = [
  { id: "ambitious", label: "Ambitious", hint: "Reach schools — worth a shot", color: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200" },
  { id: "target", label: "Target", hint: "Realistic fits for your profile", color: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200" },
  { id: "safe", label: "Safe", hint: "Strong odds of admission", color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" },
] as const;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  );
}

function MatchCard({ m, starred, onStar }: { m: Match; starred: boolean; onStar: () => void }) {
  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold leading-snug">{m.university}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {m.program} · {m.city}, {m.country}
          </p>
        </div>
        <button
          onClick={onStar}
          aria-label={starred ? "Remove from shortlist" : "Add to shortlist"}
          className={`shrink-0 rounded-full px-2.5 py-1 text-sm ${starred ? "bg-amber-400 text-amber-950" : "border border-gray-300 dark:border-gray-700"}`}
        >
          {starred ? "★ Saved" : "☆ Save"}
        </button>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Stat label="Admit odds" value={`${Math.round(m.chance * 100)}%`} />
        <Stat label="Total cost" value={`₹${m.total_cost_lakhs}L`} />
        <Stat label="Median salary" value={`₹${m.salary_lakhs}L/yr`} />
        <Stat label="Payback" value={m.payback_years == null ? "10+ yrs" : `~${m.payback_years} yrs`} />
      </dl>

      <p className="text-sm">{m.why}</p>
      <p className="text-sm text-amber-700 dark:text-amber-300">⚠ {m.watch_out}</p>

      <div className="flex flex-wrap gap-2 text-xs text-gray-500">
        {m.qs_rank && <span>QS ~#{m.qs_rank}</span>}
        <span>{m.duration_months} months</span>
        {m.stem && <span>STEM</span>}
        <span>Deadline ~{MONTHS[m.deadline_month - 1]}</span>
        {m.funding_gap_lakhs > 0 && <span className="text-indigo-600 dark:text-indigo-400">Funding gap ₹{m.funding_gap_lakhs}L</span>}
      </div>

      <Link
        href={`/programs/${m.course_id}`}
        className="mt-auto rounded-lg border border-indigo-200 px-3 py-2 text-center text-sm font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-900 dark:text-indigo-300 dark:hover:bg-indigo-950"
      >
        What-if odds &amp; ROI →
      </Link>
    </article>
  );
}

export default function NavigatorPage() {
  const { me, loading, error: meError } = useMe();
  const [result, setResult] = useState<NavResult | null>(null);
  const [shortlist, setShortlist] = useState<number[]>([]);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    setError("");
    try {
      const r = await api<NavResult>("/navigator/run", { method: "POST" });
      setResult(r);
      setShortlist(r.shortlist);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    if (me?.profile) run();
  }, [me]);

  async function toggle(courseId: number) {
    const on = shortlist.includes(courseId);
    const r = await api<{ shortlist: number[] }>(`/navigator/shortlist/${courseId}`, { method: on ? "DELETE" : "POST" });
    setShortlist(r.shortlist);
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (meError) return <main className="p-6 text-red-600">Could not reach the backend: {meError}</main>;

  if (me && !me.profile) {
    return (
      <main className="mx-auto max-w-xl space-y-4 p-6 text-center">
        <h1 className="text-2xl font-bold">Career Navigator</h1>
        <p className="text-gray-600 dark:text-gray-400">Take the 2-minute quiz first so we can match you to programs.</p>
        <Link href="/onboarding" className="inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white">
          Start the quiz
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
          ← Dashboard
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Career Navigator</h1>
          <button
            onClick={run}
            disabled={running}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-gray-700"
          >
            {running ? "Matching…" : "Refresh matches"}
          </button>
        </div>
        {me?.profile && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {me.profile.target_countries.join(", ")} · {me.profile.target_intake} ·{" "}
            <Link href="/onboarding" className="text-indigo-600 hover:underline">
              edit profile
            </Link>
          </p>
        )}
      </header>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}

      {!result && running && <p className="text-gray-500">Finding programs that fit you…</p>}

      {result && (
        <>
          <section className="rounded-xl bg-indigo-50 p-4 text-sm text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide">{result.ai ? "✨ AI strategy" : "Summary"}</p>
            <p>{result.summary}</p>
            {result.notice && <p className="mt-2 text-xs opacity-75">{result.notice}</p>}
          </section>

          {BUCKETS.map((b) => {
            const items = result.matches.filter((m) => m.bucket === b.id);
            if (!items.length) return null;
            return (
              <section key={b.id} className="space-y-3">
                <div className="flex items-baseline gap-3">
                  <span className={`rounded-full px-3 py-1 text-sm font-semibold ${b.color}`}>{b.label}</span>
                  <span className="text-sm text-gray-500">{b.hint}</span>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {items.map((m) => (
                    <MatchCard key={m.course_id} m={m} starred={shortlist.includes(m.course_id)} onStar={() => toggle(m.course_id)} />
                  ))}
                </div>
              </section>
            );
          })}

          <p className="text-xs text-gray-500">
            {result.disclaimer} Admit odds are estimates from our model, not guarantees. Costs include living, visa/flights and a rupee buffer; payback assumes 35% of salary goes to recovering the cost plus loan interest.
          </p>
        </>
      )}
    </main>
  );
}
