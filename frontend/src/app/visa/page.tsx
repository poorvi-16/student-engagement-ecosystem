"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Turn = {
  id: string;
  question: string;
  answer: string;
  rating: number;
  feedback: string;
  tip: string;
  red_flags: string[];
  follow_up: string | null;
  follow_up_of?: string;
  ai: boolean;
};

type Interview = {
  id: number;
  country: string;
  visa: string;
  program_label: string;
  status: "active" | "done" | "abandoned";
  turns: Turn[];
  current: { id: string; text: string; follow_up_of?: string } | null;
  progress: { asked: number; total: number };
  score: number | null;
  ai: boolean;
  summary?: { score: number; verdict: string; focus: { question: string; rating: number; tip: string }[]; red_flags: string[] };
};

type Overview = {
  countries: { id: string; label: string }[];
  default_country: string;
  programs: { course_id: number; country: string; label: string }[];
  active: Interview | null;
  history: { id: number; country: string; program_label: string; score: number | null; created_at: string }[];
};

// Minimal typing for the browser speech APIs (Chrome/Edge expose webkitSpeechRecognition)
type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
};

function Stars({ n }: { n: number }) {
  return (
    <span aria-label={`${n} out of 5`} className="tracking-tight">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={i <= n ? "text-amber-500" : "text-gray-300 dark:text-gray-700"}>
          ★
        </span>
      ))}
    </span>
  );
}

function Feedback({ t }: { t: Turn }) {
  const tone = t.rating >= 4 ? "border-emerald-200 dark:border-emerald-900" : t.rating >= 3 ? "border-amber-200 dark:border-amber-900" : "border-rose-200 dark:border-rose-900";
  return (
    <div className={`ml-auto max-w-[92%] space-y-1.5 rounded-xl border bg-white p-3 text-sm dark:bg-gray-950 ${tone}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{t.ai ? "Coach" : "Quick check"}</span>
        <Stars n={t.rating} />
      </div>
      <p>{t.feedback}</p>
      {t.tip && <p className="text-gray-600 dark:text-gray-400">💡 {t.tip}</p>}
      {t.red_flags.length > 0 && <p className="text-xs text-rose-600">🚩 {t.red_flags.join(" · ")}</p>}
    </div>
  );
}

export default function VisaPage() {
  const { me, loading } = useMe();
  const [ov, setOv] = useState<Overview | null>(null);
  const [country, setCountry] = useState("USA");
  const [courseId, setCourseId] = useState("");
  const [iv, setIv] = useState<Interview | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [speak, setSpeak] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const [canListen, setCanListen] = useState(false);

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
    setCanListen(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  useEffect(() => {
    if (!me) return;
    api<Overview>("/visa")
      .then((o) => {
        setOv(o);
        setCountry(o.default_country);
        const match = o.programs.find((p) => p.country === o.default_country);
        if (match) setCourseId(String(match.course_id));
        if (o.active) setIv(o.active);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me]);

  // Read the officer's question aloud when enabled
  const question = iv?.status === "active" ? iv.current?.text : undefined;
  useEffect(() => {
    if (!speak || !question || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(question);
    u.lang = "en-US";
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  }, [speak, question]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [iv?.turns.length, iv?.status]);

  async function start() {
    setBusy(true);
    setError("");
    setNotice(null);
    try {
      setIv(await api<Interview>("/visa/start", { method: "POST", body: JSON.stringify({ country, course_id: courseId ? Number(courseId) : null }) }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!iv || !answer.trim()) return;
    rec.current?.stop();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ interview: Interview; notice: string | null; xp_awarded: number }>(`/visa/${iv.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      });
      setIv(r.interview);
      setNotice(r.notice);
      setAnswer("");
      if (r.interview.status === "done") api<Overview>("/visa").then(setOv).catch(() => {});
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleMic() {
    if (listening) {
      rec.current?.stop();
      return;
    }
    const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = "en-IN";
    r.interimResults = false;
    const before = answer;
    r.onresult = (e) => {
      const text = Array.from(e.results)
        .map((res) => res[0].transcript)
        .join(" ");
      setAnswer((before ? before + " " : "") + text);
    };
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  const programsForCountry = ov?.programs.filter((p) => p.country === country) ?? [];

  return (
    <main className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
          ← Dashboard
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-2xl font-bold">Visa mock interview</h1>
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} className="accent-indigo-600" />
            🔊 Read questions aloud
          </label>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Practise with an AI visa officer. You get feedback after every answer and a readiness score at the end.
        </p>
      </header>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}

      {(!iv || iv.status !== "active") && ov && (
        <section className="space-y-3 rounded-xl border border-gray-200 p-4 sm:p-5 dark:border-gray-800">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="font-medium">Country</span>
              <select
                value={country}
                onChange={(e) => {
                  setCountry(e.target.value);
                  const m = ov.programs.find((p) => p.country === e.target.value);
                  setCourseId(m ? String(m.course_id) : "");
                }}
                className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700"
              >
                {ov.countries.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} — {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium">Program</span>
              <select
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700"
              >
                {programsForCountry.map((p) => (
                  <option key={p.course_id} value={p.course_id}>
                    {p.label}
                  </option>
                ))}
                <option value="">Not chosen yet</option>
              </select>
            </label>
          </div>
          <p className="text-xs text-gray-500">
            The officer sees your program and funding plan (cost and loan needed), so answer as you would for real.
            {programsForCountry.length === 0 && " Save a program in this country in the Navigator for a more realistic interview."}
          </p>
          <button onClick={start} disabled={busy} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
            {busy ? "Starting…" : iv?.status === "done" ? "Practise again" : "Start interview · +50 XP"}
          </button>
        </section>
      )}

      {iv && (
        <section className="space-y-3 rounded-xl bg-gray-50 p-3 sm:p-4 dark:bg-gray-900/50">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
            <span>
              🛂 {iv.visa}
              {iv.program_label && ` · ${iv.program_label}`}
            </span>
            <span>
              Question {Math.min(iv.progress.asked + (iv.status === "active" ? 1 : 0), iv.progress.total)} of {iv.progress.total}
            </span>
          </div>

          {iv.turns.map((t, i) => (
            <div key={i} className="space-y-2">
              <p className="max-w-[88%] rounded-2xl rounded-bl-sm border border-gray-200 bg-white px-4 py-2.5 text-sm dark:border-gray-800 dark:bg-gray-950">
                <span className="mr-1">👮</span>
                {t.question}
              </p>
              <p className="ml-auto max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm text-white">{t.answer}</p>
              <Feedback t={t} />
            </div>
          ))}

          {iv.status === "active" && iv.current && (
            <div className="space-y-2">
              <p className="max-w-[88%] rounded-2xl rounded-bl-sm border border-indigo-300 bg-white px-4 py-2.5 text-sm font-medium dark:border-indigo-800 dark:bg-gray-950">
                <span className="mr-1">👮</span>
                {iv.current.follow_up_of && <span className="mr-1 text-xs font-normal text-indigo-600">Follow-up:</span>}
                {iv.current.text}
              </p>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
                }}
                rows={3}
                maxLength={1500}
                placeholder="Answer as you would to the officer (2–4 sentences)…"
                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-950"
              />
              <div className="flex flex-wrap items-center justify-end gap-2">
                {canListen && (
                  <button
                    onClick={toggleMic}
                    className={`rounded-lg border px-3 py-2 text-sm ${listening ? "border-rose-400 text-rose-600" : "border-gray-300 dark:border-gray-700"}`}
                  >
                    {listening ? "■ Stop" : "🎙️ Speak"}
                  </button>
                )}
                <button
                  onClick={submit}
                  disabled={busy || !answer.trim()}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {busy ? "Officer is thinking…" : "Answer"}
                </button>
              </div>
            </div>
          )}

          {iv.status === "done" && iv.summary && (
            <div className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className="text-4xl font-bold tabular-nums">{iv.summary.score}</p>
                  <p className="text-[11px] uppercase tracking-wide text-gray-500">Readiness</p>
                </div>
                <p className="text-sm">{iv.summary.verdict}</p>
              </div>
              {iv.summary.focus.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Practise these answers</p>
                  {iv.summary.focus.map((f, i) => (
                    <div key={i} className="rounded-lg bg-gray-50 p-2.5 text-sm dark:bg-gray-900">
                      <p className="font-medium">
                        {f.question} <Stars n={f.rating} />
                      </p>
                      <p className="text-gray-600 dark:text-gray-400">💡 {f.tip}</p>
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[11px] text-gray-500">
                Practice only. Real decisions are made by visa officers based on your documents and interview.
              </p>
            </div>
          )}
          <div ref={bottom} />
        </section>
      )}

      {notice && <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">{notice}</p>}

      {ov && ov.history.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Past interviews</h2>
          <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200 text-sm dark:divide-gray-800 dark:border-gray-800">
            {ov.history.map((h) => (
              <li key={h.id}>
                <button
                  onClick={() => api<Interview>(`/visa/${h.id}`).then(setIv)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-900"
                >
                  <span className="min-w-0 truncate">
                    {h.country}
                    {h.program_label && ` · ${h.program_label}`} <span className="text-gray-500">· {new Date(h.created_at).toLocaleDateString("en-IN")}</span>
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums">{h.score}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
