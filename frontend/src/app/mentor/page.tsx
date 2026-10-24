"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Source = { ref: string; title: string; section: string; url: string };

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  tools: string[];
  ai: boolean;
  created_at: string;
};

const TOOL_LABELS: Record<string, string> = {
  search_knowledge: "🔎 Searched guides",
  find_programs: "🎓 Checked programs",
  analyze_program: "📊 Ran odds & ROI",
  estimate_loan: "💰 Checked loan offers",
};

/** Renders plain text with "- " bullets and turns [S1] / [S1, S2] into links to the cited source. */
function Rich({ text, sources }: { text: string; sources: Source[] }) {
  const byRef = Object.fromEntries(sources.map((s) => [s.ref, s]));

  function inline(line: string) {
    return line.split(/(\[S\d+(?:\s*,\s*S\d+)*\])/g).map((part, i) => {
      const refs = part.match(/S\d+/g);
      if (!part.startsWith("[") || !refs) return <Fragment key={i}>{part}</Fragment>;
      return (
        <sup key={i} className="ml-0.5 space-x-0.5">
          {refs.map((r) =>
            byRef[r] ? (
              <a
                key={r}
                href={byRef[r].url}
                target="_blank"
                rel="noreferrer"
                title={`${byRef[r].title} — ${byRef[r].section}`}
                className="rounded bg-indigo-100 px-1 text-[10px] font-semibold text-indigo-700 no-underline dark:bg-indigo-950 dark:text-indigo-300"
              >
                {r.slice(1)}
              </a>
            ) : null,
          )}
        </sup>
      );
    });
  }

  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul${blocks.length}`} className="list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (/^[-•*]\s+/.test(line)) bullets.push(line.replace(/^[-•*]\s+/, ""));
    else {
      flush();
      if (line) blocks.push(<p key={`p${blocks.length}`}>{inline(line.replace(/\*\*/g, ""))}</p>);
    }
  }
  flush();
  return <div className="space-y-2">{blocks}</div>;
}

function Bubble({ m }: { m: Message }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-white">{m.content}</p>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] space-y-2 rounded-2xl rounded-bl-sm border border-gray-200 bg-white px-4 py-3 text-sm leading-relaxed dark:border-gray-800 dark:bg-gray-950">
        {m.tools.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {m.tools.map((t) => (
              <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-900 dark:text-gray-400">
                {TOOL_LABELS[t] ?? t}
              </span>
            ))}
          </div>
        )}
        <Rich text={m.content} sources={m.sources} />
        {m.sources.length > 0 && (
          <div className="border-t border-gray-100 pt-2 dark:border-gray-800">
            <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Sources</p>
            <ol className="mt-1 space-y-0.5 text-xs">
              {m.sources.map((s) => (
                <li key={s.ref}>
                  <span className="mr-1 font-semibold text-indigo-600">{s.ref.slice(1)}.</span>
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-gray-700 hover:underline dark:text-gray-300">
                    {s.title} — {s.section}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MentorPage() {
  const { me, loading } = useMe();
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!me) return;
    api<{ messages: Message[]; suggestions: string[] }>("/mentor/history")
      .then((h) => {
        setMessages(h.messages);
        setSuggestions(h.suggestions);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me]);

  // Other pages can open the mentor with a question ready to send: /mentor?q=...
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setInput(q.slice(0, 1000));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setInput("");
    setError(null);
    setSending(true);
    const temp: Message = { id: -Date.now(), role: "user", content: message, sources: [], tools: [], ai: true, created_at: "" };
    setMessages((ms) => [...ms, temp]);
    try {
      const r = await api<{ message: Message; notice: string | null }>("/mentor/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setMessages((ms) => [...ms, r.message]);
      setNotice(r.notice);
    } catch (e) {
      setMessages((ms) => ms.filter((m) => m.id !== temp.id));
      setInput(message);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  async function clear() {
    await api("/mentor/history", { method: "DELETE" });
    setMessages([]);
    setNotice(null);
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  return (
    <main className="mx-auto flex h-dvh max-w-3xl flex-col p-4 sm:p-6">
      <header className="flex items-center justify-between gap-2 pb-3">
        <div>
          <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
            ← Dashboard
          </Link>
          <h1 className="text-xl font-bold">AI Mentor</h1>
        </div>
        {messages.length > 0 && (
          <button onClick={clear} className="text-sm text-gray-500 hover:underline">
            Clear chat
          </button>
        )}
      </header>

      <section className="flex-1 space-y-4 overflow-y-auto rounded-xl bg-gray-50 p-3 sm:p-4 dark:bg-gray-900/50">
        {messages.length === 0 && !sending && (
          <div className="py-8 text-center">
            <p className="text-3xl">🧑‍🏫</p>
            <p className="mt-2 font-medium">Ask me anything about studying abroad or in India</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-gray-600 dark:text-gray-400">
              Visas, tests, deadlines, costs, scholarships and education loans. I know your profile, can check your
              admit chances, and cite my sources.
            </p>
            {!me?.profile && (
              <p className="mt-3 text-sm">
                <Link href="/onboarding" className="text-indigo-600 hover:underline">
                  Take the quiz
                </Link>{" "}
                for personalised answers.
              </p>
            )}
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <p className="animate-pulse rounded-2xl rounded-bl-sm border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-950">
              Thinking… checking guides and your profile
            </p>
          </div>
        )}
        <div ref={bottom} />
      </section>

      {(notice || error) && (
        <p className={`mt-2 rounded-lg p-2 text-xs ${error ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200" : "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200"}`}>
          {error ?? notice}
        </p>
      )}

      {messages.length < 2 && suggestions.length > 0 && (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              disabled={sending}
              className="shrink-0 rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:border-indigo-900 dark:bg-gray-950 dark:text-indigo-300"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={1000}
          placeholder="e.g. Do I need collateral for a ₹40L loan?"
          className="min-w-0 flex-1 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-950"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
      <p className="mt-2 text-center text-[11px] text-gray-500">
        AI answers can be wrong. Check visa and fee rules on official websites. Loan information is indicative.
      </p>
    </main>
  );
}
