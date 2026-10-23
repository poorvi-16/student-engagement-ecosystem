"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api";

const CATEGORIES = [
  { id: "bug", label: "Something's broken" },
  { id: "idea", label: "I have an idea" },
  { id: "other", label: "Other" },
] as const;

/** Floating feedback button for signed-in testers; messages land in the admin console. */
export function FeedbackButton() {
  const { session } = useAuth();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]["id"]>("other");
  const [rating, setRating] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  if (!session) return null;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      await api("/feedback", { method: "POST", body: JSON.stringify({ category, rating, message, page: path }) });
      setState("sent");
      setMessage("");
      setRating(null);
      setTimeout(() => {
        setOpen(false);
        setState("idle");
      }, 1800);
    } catch {
      setState("error");
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-20 print:hidden">
      {open ? (
        <form onSubmit={send} className="w-80 max-w-[calc(100vw-2rem)] space-y-3 rounded-2xl border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-700 dark:bg-gray-950">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Send feedback</h2>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="text-gray-400 hover:text-gray-600">
              ✕
            </button>
          </div>
          {state === "sent" ? (
            <p className="py-4 text-center text-sm text-emerald-600">Thank you! We read every message.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setCategory(c.id)}
                    className={`rounded-full px-2.5 py-1 text-xs ${category === c.id ? "bg-indigo-600 text-white" : "border border-gray-300 dark:border-gray-700"}`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              <textarea
                required
                minLength={3}
                maxLength={2000}
                rows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="What happened, or what would make this better?"
                className="w-full rounded-lg border border-gray-300 bg-transparent p-2 text-sm dark:border-gray-700"
              />
              <div className="flex items-center gap-1 text-lg" aria-label="Rating">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} type="button" onClick={() => setRating(rating === n ? null : n)} className={rating && n <= rating ? "text-amber-400" : "text-gray-300"} aria-label={`${n} star`}>
                    ★
                  </button>
                ))}
                <span className="ml-2 text-xs text-gray-500">optional</span>
              </div>
              {state === "error" && <p className="text-xs text-red-600">Couldn&apos;t send. Please try again.</p>}
              <button disabled={state === "sending"} className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                {state === "sending" ? "Sending…" : "Send"}
              </button>
            </>
          )}
        </form>
      ) : (
        <button onClick={() => setOpen(true)} className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-lg hover:bg-indigo-700">
          💬 Feedback
        </button>
      )}
    </div>
  );
}
