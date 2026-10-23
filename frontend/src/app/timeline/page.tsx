"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Task = {
  id: number;
  key: string;
  title: string;
  detail: string;
  category: string;
  due_date: string;
  fixed: boolean;
  course_id: number | null;
  source: "rule" | "ai";
  done: boolean;
};

type Plan = {
  intake: string | null;
  start_date: string | null;
  main_country: string | null;
  summary: string;
  warning: string | null;
  ai: boolean;
  generated_at: string;
};

type TimelineResponse = {
  plan: Plan | null;
  tasks: Task[];
  progress: { done: number; total: number };
  today?: string;
  stale: boolean;
  notice: string | null;
};

const CATEGORY: Record<string, { label: string; icon: string }> = {
  research: { label: "Research", icon: "🔎" },
  tests: { label: "Tests", icon: "📝" },
  documents: { label: "Documents", icon: "📄" },
  sop: { label: "SOP", icon: "✍️" },
  lor: { label: "LORs", icon: "🤝" },
  applications: { label: "Applications", icon: "🎓" },
  scholarships: { label: "Scholarships", icon: "🏅" },
  finance: { label: "Funding", icon: "💰" },
  visa: { label: "Visa", icon: "🛂" },
  travel: { label: "Travel", icon: "✈️" },
};

// Tasks that have a matching PathPilot tool
const TOOL_LINKS: [RegExp, string, string][] = [
  [/^research:/, "/navigator", "Open Navigator"],
  [/^sop:review/, "/sop", "Open SOP reviewer"],
  [/^visa:usa:3/, "/visa", "Start mock interview"],
  [/^finance:estimate/, "/navigator", "See funding gaps"],
];

const monthKey = (d: string) => d.slice(0, 7);
const monthLabel = (k: string) => new Date(`${k}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
const dayLabel = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

export default function TimelinePage() {
  const { me, loading, setMe } = useMe();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hideDone, setHideDone] = useState(false);
  const [toast, setToast] = useState("");

  async function generate() {
    setBusy(true);
    setError("");
    try {
      setData(await api<TimelineResponse>("/timeline/generate", { method: "POST" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!me?.profile) return;
    api<TimelineResponse>("/timeline")
      .then((d) => (d.plan ? setData(d) : generate()))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me?.profile]);

  async function toggle(t: Task) {
    setData((d) => d && { ...d, tasks: d.tasks.map((x) => (x.id === t.id ? { ...x, done: !t.done } : x)) });
    try {
      const r = await api<{ task: Task; xp_awarded: number; user_xp: number }>(`/timeline/tasks/${t.id}`, {
        method: "PATCH",
        body: JSON.stringify({ done: !t.done }),
      });
      if (r.xp_awarded) {
        setToast(`+${r.xp_awarded} XP`);
        setTimeout(() => setToast(""), 1800);
        setMe((m) => m && { ...m, user: { ...m.user, xp: r.user_xp } });
      }
    } catch (e) {
      setData((d) => d && { ...d, tasks: d.tasks.map((x) => (x.id === t.id ? { ...x, done: t.done } : x)) });
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (me && !me.profile) {
    return (
      <main className="mx-auto max-w-xl space-y-4 p-6 text-center">
        <h1 className="text-2xl font-bold">Application timeline</h1>
        <p className="text-gray-600 dark:text-gray-400">Take the 2-minute quiz first so we can plan your months.</p>
        <Link href="/onboarding" className="inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white">
          Start the quiz
        </Link>
      </main>
    );
  }

  const today = data?.today ?? new Date().toISOString().slice(0, 10);
  const tasks = (data?.tasks ?? []).filter((t) => !hideDone || !t.done);
  const months = [...new Set(tasks.map((t) => monthKey(t.due_date)))];
  const done = data?.tasks.filter((t) => t.done).length ?? 0;
  const total = data?.tasks.length ?? 0;
  const next = data?.tasks.find((t) => !t.done);

  return (
    <main className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
          ← Dashboard
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Application timeline</h1>
          <button
            onClick={generate}
            disabled={busy}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-gray-700"
          >
            {busy ? "Planning…" : "Regenerate"}
          </button>
        </div>
        {data?.plan && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {data.plan.intake} · {data.plan.main_country} · course starts ~
            {data.plan.start_date && monthLabel(monthKey(data.plan.start_date))}
          </p>
        )}
      </header>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
      {!data && busy && <p className="text-gray-500">Building your month-by-month plan…</p>}

      {data?.plan && (
        <>
          {data.stale && (
            <p className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
              Your profile or shortlist changed since this plan was made.
              <button onClick={generate} disabled={busy} className="font-medium underline">
                Update plan
              </button>
            </p>
          )}
          {data.plan.warning && (
            <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-200">⚠ {data.plan.warning}</p>
          )}

          <section className="space-y-3 rounded-xl bg-indigo-50 p-4 text-sm text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100">
            <p className="text-xs font-semibold uppercase tracking-wide">{data.plan.ai ? "✨ Your plan" : "Your plan"}</p>
            <p>{data.plan.summary}</p>
            {data.notice && <p className="text-xs opacity-75">{data.notice}</p>}
            <div>
              <div className="flex justify-between text-xs">
                <span>
                  {done} of {total} done
                </span>
                {next && (
                  <span>
                    Next: {next.title} · {dayLabel(next.due_date)}
                  </span>
                )}
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/70 dark:bg-indigo-900">
                <div className="h-full bg-indigo-600 transition-all" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
              </div>
            </div>
          </section>

          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} className="accent-indigo-600" />
            Hide completed
          </label>

          <ol className="space-y-6">
            {months.map((mk) => {
              const current = mk === monthKey(today);
              return (
                <li key={mk} className="space-y-2">
                  <h2 className={`text-sm font-semibold uppercase tracking-wide ${current ? "text-indigo-600" : "text-gray-500"}`}>
                    {monthLabel(mk)} {current && "· this month"}
                  </h2>
                  <ul className="space-y-2">
                    {tasks
                      .filter((t) => monthKey(t.due_date) === mk)
                      .map((t) => {
                        const overdue = !t.done && t.due_date < today;
                        const cat = CATEGORY[t.category] ?? { label: t.category, icon: "•" };
                        const tool = TOOL_LINKS.find(([re]) => re.test(t.key));
                        return (
                          <li
                            key={t.id}
                            className={`flex gap-3 rounded-xl border p-3 ${t.done ? "border-gray-100 opacity-60 dark:border-gray-900" : overdue ? "border-rose-300 dark:border-rose-900" : "border-gray-200 dark:border-gray-800"}`}
                          >
                            <input
                              type="checkbox"
                              checked={t.done}
                              onChange={() => toggle(t)}
                              aria-label={`Mark "${t.title}" done`}
                              className="mt-1 h-4 w-4 shrink-0 accent-indigo-600"
                            />
                            <div className="min-w-0 flex-1 space-y-1">
                              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                                <p className={`font-medium ${t.done ? "line-through" : ""}`}>{t.title}</p>
                                <span className={`text-xs tabular-nums ${overdue ? "font-semibold text-rose-600" : "text-gray-500"}`}>
                                  {t.fixed ? "Deadline " : "By "}
                                  {dayLabel(t.due_date)}
                                  {overdue && " · overdue"}
                                </span>
                              </div>
                              <p className="text-sm text-gray-600 dark:text-gray-400">{t.detail}</p>
                              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-600 dark:bg-gray-900 dark:text-gray-400">
                                  {cat.icon} {cat.label}
                                </span>
                                {t.source === "ai" && (
                                  <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                                    ✨ suggested for you
                                  </span>
                                )}
                                {t.course_id && (
                                  <Link href={`/programs/${t.course_id}`} className="text-indigo-600 hover:underline">
                                    Odds &amp; ROI →
                                  </Link>
                                )}
                                {tool && (
                                  <Link href={tool[1]} className="text-indigo-600 hover:underline">
                                    {tool[2]} →
                                  </Link>
                                )}
                              </div>
                            </div>
                          </li>
                        );
                      })}
                  </ul>
                </li>
              );
            })}
          </ol>
          <p className="text-xs text-gray-500">
            Dates come from typical deadlines and visa processing times. Always confirm exact dates on official university and
            embassy websites. +10 XP for every task you complete.
          </p>
        </>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-amber-400 px-4 py-2 text-sm font-semibold text-amber-950 shadow-lg">
          {toast}
        </div>
      )}
    </main>
  );
}
