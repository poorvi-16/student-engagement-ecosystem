"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Scope = "real" | "sim" | "all";
type FunnelStep = { key: string; label: string; users: number; pct_of_signups: number; pct_of_previous: number | null };
type Variant = { exposures: number; clicks: number; ctr: number };
type Overview = {
  students: { real: number; simulated: number };
  funnel: FunnelStep[];
  series: { date: string; signups: number; active: number; loan_submitted: number }[];
  attribution: { source: string; campaign: string; signups: number }[];
  ab: { variants: Record<string, Variant>; leader: string; z: number; significant: boolean; lift_b_vs_a: number | null };
  content: { posts: number; guides: number; views: number; ai_written: number; topics: { topic: string; guides: number; views: number }[]; top: { slug: string; title: string; views: number; ai: boolean }[] };
  llm: {
    calls_24h: number;
    by_feature: { feature: string; calls: number; tokens: number }[];
    by_model: { model: string; calls: number }[];
    month_cost_usd: number;
    monthly_budget_usd: number;
    daily_limit_per_user: number;
    keys: Record<string, boolean>;
    paused: boolean;
    global_daily_calls: number;
  };
  models: { admit: Record<string, string | number>; lead: Record<string, string | number> };
};
type Step = { key: string; name: string; status: string; detail: string; ms: number };
type Run = { id: number; trigger: string; status: string; summary: string; started_at: string; finished_at: string | null; steps: Step[] };
type Lead = { user_id: string; name: string; simulated: boolean; stage: string; score: number; hot: boolean; submitted: boolean; funding_gap_lakhs: number; target: string | null; why: { label: string; points: number }[] };
type Feedback = { id: number; category: string; rating: number | null; message: string; page: string; status: string; created_at: string; from: string | null };
type Msg = { id: number; channel: string; status: string; variant: string | null; source: string; title: string; created_at: string };

const card = "rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5";
const STATUS: Record<string, string> = {
  ok: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  skipped: "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-400",
  partial: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  error: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  running: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
};
const pct = (x: number | null | undefined, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
const when = (s: string) => new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      {sub && <p className="text-[11px] text-gray-500">{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const { me, loading } = useMe();
  const [scope, setScope] = useState<Scope>("real");
  const [ov, setOv] = useState<Overview | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [threshold, setThreshold] = useState(0.25);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [simUsers, setSimUsers] = useState(120);
  const [simDays, setSimDays] = useState(21);
  const isAdmin = me?.user.role === "admin";

  const load = useCallback(async () => {
    const [o, r, l, m, f] = await Promise.all([
      api<Overview>(`/admin/overview?scope=${scope}`),
      api<Run[]>("/admin/agent-runs?limit=8"),
      api<{ leads: Lead[]; threshold: number }>(`/admin/leads?scope=${scope}&limit=12`),
      api<Msg[]>("/admin/nudges?limit=12"),
      api<Feedback[]>("/admin/feedback?limit=20"),
    ]);
    setFeedback(f);
    setOv(o);
    setRuns(r);
    setLeads(l.leads);
    setThreshold(l.threshold);
    setMsgs(m);
  }, [scope]);

  useEffect(() => {
    if (isAdmin) load().catch((e) => setNote(String(e.message ?? e)));
  }, [isAdmin, load]);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setNote("");
    try {
      await fn();
      await load();
    } catch (e) {
      setNote(String((e as Error).message ?? e));
    }
    setBusy("");
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-md space-y-3 p-8 text-center">
        <p className="text-gray-600 dark:text-gray-400">The Agent Console is for admins only.</p>
        <Link href="/dashboard" className="text-indigo-600 hover:underline">
          Back to the dashboard
        </Link>
      </main>
    );
  }

  const funnel = ov?.funnel ?? [];
  const submitted = funnel.find((f) => f.key === "loan_submitted");
  const ab = ov?.ab;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/dashboard" className="text-sm text-indigo-600 hover:underline">
            ← Dashboard
          </Link>
          <h1 className="text-2xl font-bold">Agent Console</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">The growth loop, its decisions and the funnel it moves. Messages are sent on mock channels only.</p>
        </div>
        <div className="flex overflow-hidden rounded-lg border border-gray-300 text-sm dark:border-gray-700">
          {(["real", "sim", "all"] as Scope[]).map((s) => (
            <button key={s} onClick={() => setScope(s)} className={`px-3 py-1.5 ${scope === s ? "bg-indigo-600 text-white" : ""}`}>
              {s === "real" ? "Real students" : s === "sim" ? "Simulated" : "All"}
            </button>
          ))}
        </div>
      </header>

      {note && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{note}</p>}
      {!ov && !note && <p className="text-gray-500">Loading the console…</p>}

      {ov && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Students" value={funnel[0]?.users ?? 0} sub={`${ov.students.real} real · ${ov.students.simulated} simulated`} />
            <Stat label="Loan applications" value={submitted?.users ?? 0} sub={`${pct(submitted?.pct_of_signups)} of sign-ups`} />
            <Stat label="Guides" value={ov.content.guides} sub={`${ov.content.views} views · ${ov.content.ai_written} AI-written`} />
            <Stat label="AI calls (24h)" value={ov.llm.calls_24h} sub={`${ov.llm.keys.gemini ? "Gemini" : ""}${ov.llm.keys.gemini && ov.llm.keys.groq ? " + " : ""}${ov.llm.keys.groq ? "Groq" : ""} free tiers`} />
          </section>

          <section className={`${card} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">Growth orchestrator</h2>
              <div className="flex flex-wrap gap-2">
                <button
                  disabled={!!busy}
                  onClick={() => act("run", () => api("/admin/orchestrator/run", { method: "POST", body: JSON.stringify({ content_topics: 2 }) }))}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
                >
                  {busy === "run" ? "Running… (up to a minute)" : "Run the loop now"}
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-500">Simulate → Learn → Acquire → Nurture → Convert → Measure. Runs daily at 10:00 IST; every decision below is logged.</p>
            {runs.length === 0 && <p className="text-sm text-gray-500">No runs yet. Press the button to run the loop.</p>}
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {runs.map((r) => (
                <li key={r.id} className="py-2">
                  <button onClick={() => setOpen(open === r.id ? null : r.id)} className="flex w-full flex-wrap items-center gap-2 text-left text-sm">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS[r.status] ?? STATUS.running}`}>{r.status}</span>
                    <span className="font-medium">Run #{r.id}</span>
                    <span className="text-gray-500">
                      {when(r.started_at)} · {r.trigger}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-gray-600 dark:text-gray-400">{r.summary}</span>
                    <span className="text-gray-400">{open === r.id ? "▲" : "▼"}</span>
                  </button>
                  {open === r.id && (
                    <ol className="mt-2 space-y-1.5 border-l-2 border-indigo-200 pl-4 dark:border-indigo-900">
                      {r.steps.map((s) => (
                        <li key={s.key} className="text-sm">
                          <span className={`mr-2 rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS[s.status] ?? ""}`}>{s.name}</span>
                          <span className="text-gray-700 dark:text-gray-300">{s.detail}</span>
                          <span className="ml-2 text-xs text-gray-400">{s.ms} ms</span>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className={card}>
              <h2 className="mb-3 font-semibold">Funnel</h2>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={funnel} layout="vertical" margin={{ left: 10, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} fontSize={11} />
                    <YAxis type="category" dataKey="label" width={150} fontSize={11} />
                    <Tooltip />
                    <Bar dataKey="users" fill="#6366f1" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <table className="mt-2 w-full text-xs text-gray-600 dark:text-gray-400">
                <tbody>
                  {funnel.map((f) => (
                    <tr key={f.key}>
                      <td>{f.label}</td>
                      <td className="text-right">{f.users}</td>
                      <td className="w-24 text-right">{pct(f.pct_of_signups, 0)} of sign-ups</td>
                      <td className="w-20 text-right">{f.pct_of_previous == null ? "" : `${pct(f.pct_of_previous, 0)} step`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={card}>
              <h2 className="mb-3 font-semibold">Last 14 days</h2>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={ov.series} margin={{ left: -15, right: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                    <YAxis allowDecimals={false} fontSize={11} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="active" name="Active students" stroke="#6366f1" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="signups" name="Sign-ups" stroke="#10b981" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="loan_submitted" name="Loan applications" stroke="#f59e0b" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {ov.attribution.length > 0 && (
                <p className="mt-2 text-xs text-gray-500">
                  Sign-ups by source: {ov.attribution.map((a) => `${a.source}${a.campaign ? ` / ${a.campaign}` : ""} ${a.signups}`).join(" · ")}
                </p>
              )}
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className={`${card} space-y-3`}>
              <h2 className="font-semibold">Lead scores</h2>
              <p className="text-xs text-gray-500">
                Likelihood of submitting a loan application ({String(ov.models.lead.version)}, AUC {String(ov.models.lead.auc)}, trained on synthetic cohorts). Above{" "}
                {pct(threshold, 0)} the loop sends a loan-copilot nudge.
              </p>
              {leads.length === 0 && <p className="text-sm text-gray-500">No students in this view yet.</p>}
              <ul className="space-y-2">
                {leads.map((l) => (
                  <li key={l.user_id} className="text-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-20 truncate font-medium">{l.name}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                        <div className={`h-full ${l.submitted ? "bg-emerald-500" : l.hot ? "bg-amber-500" : "bg-indigo-400"}`} style={{ width: `${l.score * 100}%` }} />
                      </div>
                      <span className="w-12 text-right tabular-nums">{pct(l.score, 0)}</span>
                      <span className="w-20 text-xs text-gray-500">{l.submitted ? "submitted" : l.hot ? "hot lead" : l.stage}</span>
                    </div>
                    {l.why.length > 0 && <p className="ml-[5.5rem] text-[11px] text-gray-500">{l.why.map((w) => w.label).join(" · ")}</p>}
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-4">
              <div className={`${card} space-y-2`}>
                <h2 className="font-semibold">Nudge copy A/B</h2>
                {ab && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      {(["A", "B"] as const).map((v) => (
                        <div key={v} className={`rounded-lg p-3 ${ab.leader === v ? "bg-emerald-50 dark:bg-emerald-950/40" : "bg-gray-50 dark:bg-gray-900"}`}>
                          <p className="text-xs text-gray-500">Copy {v}{v === "A" ? " (control)" : " (benefit-led)"}</p>
                          <p className="text-xl font-semibold">{pct(ab.variants[v]?.ctr)}</p>
                          <p className="text-[11px] text-gray-500">
                            {ab.variants[v]?.clicks ?? 0} clicks / {ab.variants[v]?.exposures ?? 0} shown
                          </p>
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">
                      {(ab.variants.A?.exposures ?? 0) < 20 || (ab.variants.B?.exposures ?? 0) < 20
                        ? "Collecting data: copy is split evenly until each variant has 20 impressions."
                        : `Copy ${ab.leader} is ahead${ab.lift_b_vs_a != null ? ` (B vs A: ${ab.lift_b_vs_a >= 0 ? "+" : ""}${(ab.lift_b_vs_a * 100).toFixed(0)}%)` : ""}, z = ${ab.z}, ${ab.significant ? "statistically significant at 95%" : "not yet significant"}. The loop serves the leader to ~80% of students.`}
                    </p>
                  </>
                )}
              </div>

              <div className={`${card} space-y-2`}>
                <h2 className="font-semibold">Simulated cohort</h2>
                <p className="text-xs text-gray-500">
                  Synthetic students with invented behaviour, so the loop has something to learn from. Flagged in the database and removable. Not evidence about real students.
                </p>
                <div className="flex flex-wrap items-end gap-2 text-sm">
                  <label className="text-xs text-gray-500">
                    Students
                    <input type="number" min={10} max={300} value={simUsers} onChange={(e) => setSimUsers(+e.target.value)} className="mt-0.5 block w-20 rounded border border-gray-300 bg-transparent px-2 py-1 dark:border-gray-700" />
                  </label>
                  <label className="text-xs text-gray-500">
                    Days
                    <input type="number" min={1} max={45} value={simDays} onChange={(e) => setSimDays(+e.target.value)} className="mt-0.5 block w-16 rounded border border-gray-300 bg-transparent px-2 py-1 dark:border-gray-700" />
                  </label>
                  <button
                    disabled={!!busy}
                    onClick={() => act("sim", () => api("/admin/simulate", { method: "POST", body: JSON.stringify({ users: simUsers, days: simDays }) }))}
                    className="rounded-lg border border-indigo-300 px-3 py-1.5 text-indigo-700 disabled:opacity-60 dark:border-indigo-800 dark:text-indigo-300"
                  >
                    {busy === "sim" ? "Simulating…" : "Add cohort"}
                  </button>
                  <button
                    disabled={!!busy || ov.students.simulated === 0}
                    onClick={() => confirm("Delete every simulated student and their data?") && act("purge", () => api("/admin/simulate", { method: "DELETE" }))}
                    className="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-50 dark:border-gray-700"
                  >
                    Remove all ({ov.students.simulated})
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className={`${card} space-y-2`}>
              <h2 className="font-semibold">Content performance</h2>
              <p className="text-xs text-gray-500">Topics with more reads get more follow-up posts; topics students are interested in get priority.</p>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-gray-500">
                  <tr>
                    <th>Topic</th>
                    <th className="text-right">Guides</th>
                    <th className="text-right">Views</th>
                  </tr>
                </thead>
                <tbody>
                  {ov.content.topics.map((t) => (
                    <tr key={t.topic}>
                      <td>{t.topic}</td>
                      <td className="text-right">{t.guides}</td>
                      <td className="text-right">{t.views}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {ov.content.top.length > 0 && (
                <p className="pt-1 text-xs text-gray-500">
                  Top guide:{" "}
                  <Link className="text-indigo-600 hover:underline" href={`/guides/${ov.content.top[0].slug}`}>
                    {ov.content.top[0].title}
                  </Link>{" "}
                  ({ov.content.top[0].views} views)
                </p>
              )}
            </div>
            <div className={`${card} space-y-2`}>
              <h2 className="font-semibold">Mock gateway log</h2>
              <p className="text-xs text-gray-500">WhatsApp and email messages are simulated: nothing leaves the system.</p>
              {msgs.length === 0 && <p className="text-sm text-gray-500">No messages yet.</p>}
              <ul className="space-y-1.5 text-sm">
                {msgs.map((m) => (
                  <li key={m.id} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-center text-[11px] dark:bg-gray-900">{m.channel === "in_app" ? "in-app" : m.channel}</span>
                    {m.variant && <span className="shrink-0 text-[11px] font-medium text-indigo-600">copy {m.variant}</span>}
                    <span className="min-w-0 flex-1 truncate">{m.title}</span>
                    <span className="shrink-0 text-xs text-gray-400">{m.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className={`${card} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-semibold">Safety switches</h2>
                <p className="text-xs text-gray-500">
                  Rate limits are on (AI actions 20/min per user, public pages 60/min per IP). All users together may make {ov.llm.global_daily_calls} AI calls per day; per
                  user {ov.llm.daily_limit_per_user}/day.
                </p>
              </div>
              <button
                disabled={!!busy}
                onClick={() => act("ai", () => api("/admin/ai", { method: "POST", body: JSON.stringify({ paused: !ov.llm.paused }) }))}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-60 ${ov.llm.paused ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}
              >
                {ov.llm.paused ? "AI is paused: resume" : "Pause all AI features"}
              </button>
            </div>
            {ov.llm.paused && <p className="text-sm text-rose-600">AI is paused for everyone. Every feature is using its non-AI fallback.</p>}
          </section>

          <section className={`${card} space-y-2`}>
            <h2 className="font-semibold">Tester feedback</h2>
            {feedback.length === 0 && <p className="text-sm text-gray-500">No feedback yet.</p>}
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {feedback.map((f) => (
                <li key={f.id} className="flex items-start gap-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <p>
                      <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] dark:bg-gray-900">{f.category}</span>
                      {f.rating ? <span className="mr-2 text-amber-500">{"★".repeat(f.rating)}</span> : null}
                      {f.message}
                    </p>
                    <p className="text-xs text-gray-500">
                      {f.from ?? "deleted user"} · {f.page || "–"} · {when(f.created_at)}
                    </p>
                  </div>
                  <button
                    onClick={() => act("fb", () => api(`/admin/feedback/${f.id}/status?status=${f.status === "done" ? "new" : "done"}`, { method: "POST" }))}
                    className="shrink-0 text-xs text-indigo-600 hover:underline"
                  >
                    {f.status === "done" ? "Reopen" : "Mark done"}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className={`${card} space-y-2`}>
            <h2 className="font-semibold">AI usage and models</h2>
            <div className="grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-xs text-gray-500">Last 24 hours by feature</p>
                <ul>
                  {ov.llm.by_feature.map((f) => (
                    <li key={f.feature} className="flex justify-between">
                      <span>{f.feature}</span>
                      <span className="text-gray-500">{f.calls} calls</span>
                    </li>
                  ))}
                  {ov.llm.by_feature.length === 0 && <li className="text-gray-500">No calls</li>}
                </ul>
              </div>
              <div>
                <p className="text-xs text-gray-500">By model (free tiers)</p>
                <ul>
                  {ov.llm.by_model.map((m) => (
                    <li key={m.model} className="flex justify-between">
                      <span className="truncate">{m.model}</span>
                      <span className="text-gray-500">{m.calls}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-gray-500">
                  Per-user limit {ov.llm.daily_limit_per_user}/day · month spend ${ov.llm.month_cost_usd} of ${ov.llm.monthly_budget_usd}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">ML models</p>
                <p>
                  Admit: {String(ov.models.admit.version)} (AUC {String(ov.models.admit.auc)})
                </p>
                <p>
                  Lead: {String(ov.models.lead.version)} (AUC {String(ov.models.lead.auc)})
                </p>
                <p className="text-xs text-gray-500">Both are trained on synthetic data until real outcomes exist.</p>
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
