"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Badge = { id: string; icon: string; name: string; how: string; earned: boolean; new: boolean };
type NudgeT = { id: number; title: string; body: string; cta_label: string; cta_href: string; priority: number };
type Growth = {
  level: { number: number; name: string; xp: number; floor: number; next_at: number | null; progress: number };
  streak_days: number;
  badges: Badge[];
  nudges: NudgeT[];
  referral: { code: string; link: string; invited: number; converted: number; reward_xp: number; perks: string };
  share_card: boolean;
};

/** Dashboard growth layer: next-best-action nudges, level + streak, badges, invites and the share card. */
export function GrowthPanel({ onXp }: { onXp?: () => void }) {
  const router = useRouter();
  const [g, setG] = useState<Growth | null>(null);
  const [toast, setToast] = useState("");
  const [copied, setCopied] = useState(false);

  function load() {
    return api<Growth>("/growth").then(setG).catch(() => {});
  }

  useEffect(() => {
    // Claim an invite code remembered from the landing page (?ref=CODE)
    let ref: string | null = null;
    try {
      ref = localStorage.getItem("pp_ref");
    } catch {}
    const claim = ref
      ? api<{ ok: boolean; message: string }>("/growth/referral", { method: "POST", body: JSON.stringify({ code: ref }) })
          .then((r) => {
            setToast(r.message);
            setTimeout(() => setToast(""), 4000);
            if (r.ok) onXp?.();
          })
          .catch(() => {})
          .finally(() => {
            try {
              localStorage.removeItem("pp_ref");
            } catch {}
          })
      : Promise.resolve();
    // Report the campaign this visitor came from (recorded once, used by the admin funnel)
    let utm: string | null = null;
    try {
      utm = localStorage.getItem("pp_utm");
    } catch {}
    if (utm) {
      api("/growth/attribution", { method: "POST", body: utm })
        .then(() => {
          try {
            localStorage.removeItem("pp_utm");
          } catch {}
        })
        .catch(() => {});
    }
    claim.then(load);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Clear "new" badge highlights a few seconds after they've been shown
  useEffect(() => {
    if (!g?.badges.some((b) => b.new)) return;
    const t = setTimeout(() => api("/growth/badges/seen", { method: "POST" }).catch(() => {}), 4000);
    return () => clearTimeout(t);
  }, [g]);

  async function act(n: NudgeT, action: "click" | "dismiss") {
    await api(`/growth/nudges/${n.id}`, { method: "POST", body: JSON.stringify({ action }) }).catch(() => {});
    if (action === "click") router.push(n.cta_href);
    else setG((x) => x && { ...x, nudges: x.nudges.filter((y) => y.id !== n.id) });
  }

  async function toggleShare(enabled: boolean) {
    const r = await api<{ share_card: boolean }>("/growth/share", { method: "POST", body: JSON.stringify({ enabled }) });
    setG((x) => x && { ...x, share_card: r.share_card });
  }

  if (!g) return null;
  const earned = g.badges.filter((b) => b.earned).length;
  const cardUrl = g.referral.link.replace(/\/\?ref=.*/, `/card/${g.referral.code}`);
  const shareText = encodeURIComponent(`I'm planning my higher studies with PathPilot. Join me and get bonus XP: ${g.referral.link}`);

  return (
    <div className="space-y-4">
      {g.nudges.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Your next steps</h2>
          {g.nudges.map((n, i) => (
            <div
              key={n.id}
              className={`flex items-start gap-3 rounded-xl border p-4 ${i === 0 ? "border-indigo-300 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950/50" : "border-gray-200 dark:border-gray-800"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="font-medium">{n.title}</p>
                <p className="text-sm text-gray-600 dark:text-gray-400">{n.body}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button onClick={() => act(n, "click")} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">
                  {n.cta_label}
                </button>
                <button onClick={() => act(n, "dismiss")} aria-label="Dismiss" className="px-1 text-gray-400 hover:text-gray-600">
                  ✕
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-semibold">
            Level {g.level.number} · {g.level.name}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {g.streak_days}🔥 day streak · {earned}/{g.badges.length} badges
          </p>
        </div>
        <div>
          <div className="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
            <div className="h-full bg-amber-400 transition-all" style={{ width: `${g.level.progress * 100}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-gray-500">
            {g.level.next_at ? `${g.level.next_at - g.level.xp} XP to level ${g.level.number + 1}` : "Top level reached"} · +5 XP for every day you visit
          </p>
        </div>
        <ul className="grid grid-cols-4 gap-2 sm:grid-cols-7">
          {g.badges.map((b) => (
            <li
              key={b.id}
              title={`${b.name}: ${b.how}`}
              className={`flex flex-col items-center rounded-lg p-2 text-center ${b.earned ? "bg-amber-50 dark:bg-amber-950/40" : "opacity-35 grayscale"} ${b.new ? "ring-2 ring-amber-400" : ""}`}
            >
              <span className="text-xl">{b.icon}</span>
              <span className="mt-0.5 text-[10px] leading-tight">{b.name}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">🤝 Invite friends</h2>
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {g.referral.invited} joined · {g.referral.converted} completed the quiz
          </span>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          You get +{g.referral.reward_xp} XP when a friend completes the quiz; they get +50 XP. {g.referral.perks}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-semibold tracking-wider dark:bg-gray-900">{g.referral.code}</code>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(g.referral.link);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700"
          >
            {copied ? "Copied!" : "Copy invite link"}
          </button>
          <a href={`https://wa.me/?text=${shareText}`} target="_blank" rel="noreferrer" className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white">
            Share on WhatsApp
          </a>
        </div>
        <label className="flex items-center gap-2 border-t border-gray-100 pt-3 text-sm dark:border-gray-800">
          <input type="checkbox" checked={g.share_card} onChange={(e) => toggleShare(e.target.checked)} className="accent-indigo-600" />
          Make my study-abroad card public (first name, goals, level and badges only)
        </label>
        {g.share_card && (
          <p className="text-sm">
            <Link href={`/card/${g.referral.code}`} className="text-indigo-600 hover:underline">
              View my card →
            </Link>{" "}
            <a
              href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(cardUrl)}`}
              target="_blank"
              rel="noreferrer"
              className="ml-3 text-indigo-600 hover:underline"
            >
              Share on LinkedIn
            </a>
          </p>
        )}
      </section>

      {toast && <div className="fixed bottom-6 left-1/2 z-10 -translate-x-1/2 rounded-full bg-indigo-600 px-4 py-2 text-sm text-white shadow-lg">{toast}</div>}
    </div>
  );
}
