"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Check = { key: string; label: string; ok: boolean; detail: string };
type Rules = { word_count: number; paragraphs: number; avg_sentence_words: number; cliches: string[]; checks: Check[]; rule_score: number };
type Review = {
  overall_score: number;
  verdict: string;
  rubric: { criterion: string; score: number; comment: string }[];
  strengths: string[];
  improvements: { issue: string; suggestion: string; quote: string }[];
  rewrite_opening: string;
};
type Summary = { id: number; program_label: string; course_id: number | null; word_count: number; score: number; ai: boolean; created_at: string };
type Full = Summary & { text: string; rules: Rules; review: Review | null; notice?: string | null };

const MIN_CHARS = 300;

function scoreBand(s: number) {
  if (s >= 75) return { label: "Nearly ready", cls: "text-emerald-600", ring: "stroke-emerald-500" };
  if (s >= 55) return { label: "Good base", cls: "text-indigo-600", ring: "stroke-indigo-500" };
  if (s >= 35) return { label: "Needs work", cls: "text-amber-600", ring: "stroke-amber-500" };
  return { label: "Rewrite", cls: "text-rose-600", ring: "stroke-rose-500" };
}

function ScoreRing({ score }: { score: number }) {
  const b = scoreBand(score);
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative h-28 w-28 shrink-0">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r={r} className="fill-none stroke-gray-200 dark:stroke-gray-800" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={r}
          className={`fill-none ${b.ring} transition-all duration-700`}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - score / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold">{score}</span>
        <span className={`text-[10px] font-medium ${b.cls}`}>{b.label}</span>
      </div>
    </div>
  );
}

function Result({ r }: { r: Full }) {
  const [copied, setCopied] = useState(false);
  const rv = r.review;
  return (
    <section className="space-y-5 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-4">
        <ScoreRing score={r.score} />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            {rv ? "✨ AI review" : "Quick checks"} · {r.program_label} · {r.word_count} words
          </p>
          <p className="font-medium">{rv ? rv.verdict : "Automatic checks on length, structure, clichés and evidence."}</p>
          {r.notice && <p className="text-xs text-amber-700 dark:text-amber-300">{r.notice}</p>}
        </div>
      </div>

      {rv && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {rv.rubric.map((x) => (
              <div key={x.criterion} className="space-y-1 rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <div className="flex justify-between text-sm">
                  <span className="font-medium">{x.criterion}</span>
                  <span className="tabular-nums text-gray-600 dark:text-gray-400">{x.score}/5</span>
                </div>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <span key={i} className={`h-1.5 flex-1 rounded-full ${i <= x.score ? "bg-indigo-500" : "bg-gray-200 dark:bg-gray-800"}`} />
                  ))}
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400">{x.comment}</p>
              </div>
            ))}
          </div>

          {rv.strengths.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">What works</p>
              <ul className="space-y-1 text-sm">
                {rv.strengths.map((s) => (
                  <li key={s}>✅ {s}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Fix these first</p>
            <ol className="space-y-2">
              {rv.improvements.map((x, i) => (
                <li key={i} className="space-y-1 rounded-lg border border-amber-200 p-3 text-sm dark:border-amber-900">
                  <p className="font-medium">
                    {i + 1}. {x.issue}
                  </p>
                  {x.quote && (
                    <blockquote className="border-l-2 border-amber-400 pl-2 text-xs italic text-gray-600 dark:text-gray-400">“{x.quote}”</blockquote>
                  )}
                  <p className="text-gray-700 dark:text-gray-300">→ {x.suggestion}</p>
                </li>
              ))}
            </ol>
          </div>

          {rv.rewrite_opening && (
            <div className="space-y-2 rounded-lg bg-indigo-50 p-4 dark:bg-indigo-950">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-indigo-900 dark:text-indigo-200">Suggested opening</p>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(rv.rewrite_opening);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="text-xs text-indigo-700 hover:underline dark:text-indigo-300"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <p className="text-sm text-indigo-950 dark:text-indigo-100">{rv.rewrite_opening}</p>
              <p className="text-[11px] text-indigo-800/80 dark:text-indigo-300/80">
                Fill in the [placeholders] with your own experiences. Admissions teams value your real story, so check every detail is true.
              </p>
            </div>
          )}
        </>
      )}

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Quick checks</p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {r.rules.checks.map((c) => (
            <li key={c.key} className="flex gap-2 text-sm">
              <span>{c.ok ? "✅" : "⚠️"}</span>
              <span>
                <span className="font-medium">{c.label}:</span> <span className="text-gray-600 dark:text-gray-400">{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function SopPage() {
  const { me, loading } = useMe();
  const [programs, setPrograms] = useState<{ course_id: number; label: string }[]>([]);
  const [history, setHistory] = useState<Summary[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<Full | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadOverview() {
    const o = await api<{ programs: { course_id: number; label: string }[]; reviews: Summary[] }>("/sop");
    setPrograms(o.programs);
    setHistory(o.reviews);
    return o;
  }

  useEffect(() => {
    if (!me) return;
    loadOverview()
      .then((o) => {
        if (o.programs.length) setCourseId(String(o.programs[0].course_id));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const r = await api<Full>("/sop/review", {
        method: "POST",
        body: JSON.stringify({ text, course_id: courseId ? Number(courseId) : null }),
      });
      setResult(r);
      loadOverview().catch(() => {});
      setTimeout(() => document.getElementById("result")?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function openPast(id: number) {
    const r = await api<Full>(`/sop/reviews/${id}`);
    setResult(r);
    setText(r.text);
    setCourseId(r.course_id ? String(r.course_id) : "");
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <main className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="text-2xl font-bold">SOP reviewer</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Paste your Statement of Purpose for a rubric score, the fixes that matter most, and a stronger opening.
        </p>
      </header>

      <section className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 sm:p-5">
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Reviewing for</span>
          <select
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700"
          >
            {programs.map((p) => (
              <option key={p.course_id} value={p.course_id}>
                {p.label}
              </option>
            ))}
            <option value="">General (no specific program)</option>
          </select>
          {programs.length === 0 && (
            <span className="text-xs text-gray-500">
              Tip: save programs in the{" "}
              <Link href="/navigator" className="text-indigo-600 hover:underline">
                Navigator
              </Link>{" "}
              to get feedback on program fit.
            </span>
          )}
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={12000}
          rows={14}
          placeholder="Paste your SOP here…"
          className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm leading-relaxed outline-none focus:border-indigo-500 dark:border-gray-700"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-gray-500">
            {words} words · Remove your name and contact details first. Your text is sent to an AI model for review.
          </p>
          <button
            onClick={submit}
            disabled={busy || text.trim().length < MIN_CHARS}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Reviewing…" : "Review my SOP · +40 XP"}
          </button>
        </div>
        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
      </section>

      <div id="result">{result && <Result r={result} />}</div>

      {history.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Past reviews</h2>
          <ul className="divide-y divide-gray-100 rounded-2xl border border-[var(--line)] bg-[var(--surface)] text-sm dark:divide-gray-800">
            {history.map((h) => (
              <li key={h.id}>
                <button onClick={() => openPast(h.id)} className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-900">
                  <span className="min-w-0 truncate">
                    {h.program_label} <span className="text-gray-500">· {h.word_count} words · {new Date(h.created_at).toLocaleDateString("en-IN")}</span>
                  </span>
                  <span className={`shrink-0 font-semibold tabular-nums ${scoreBand(h.score).cls}`}>{h.score}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
