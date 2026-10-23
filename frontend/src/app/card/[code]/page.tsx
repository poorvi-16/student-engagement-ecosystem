"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

type Card = {
  first_name: string;
  level: { number: number; name: string };
  streak_days: number;
  target: { field: string | null; countries: string[]; intake: string | null; level: string | null };
  profile_strength: number | null;
  badges: { icon: string; name: string }[];
  code: string;
};

export default function CardPage() {
  const { code } = useParams<{ code: string }>();
  const [card, setCard] = useState<Card | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/public/card/${code}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setCard)
      .catch(() => setMissing(true));
  }, [code]);

  if (missing) {
    return (
      <main className="mx-auto max-w-md space-y-4 p-6 text-center">
        <p className="text-gray-600 dark:text-gray-400">This card isn&apos;t public.</p>
        <Link href="/" className="text-indigo-600 hover:underline">
          Start your own journey with PathPilot →
        </Link>
      </main>
    );
  }
  if (!card) return <main className="p-6 text-center text-gray-500">Loading…</main>;

  const degree = card.target.level === "mba" ? "MBA" : card.target.level === "phd" ? "PhD" : "Master's";
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <article className="w-full max-w-md space-y-5 rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-700 p-7 text-white shadow-xl">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-80">PathPilot · Study card</p>
        <div>
          <h1 className="text-3xl font-bold">{card.first_name}</h1>
          <p className="mt-1 text-lg opacity-90">
            {degree} in {card.target.field ?? "—"}
          </p>
          <p className="opacity-80">
            {card.target.countries.join(" · ")}
            {card.target.intake ? ` · ${card.target.intake}` : ""}
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-white/15 p-2">
            <dt className="text-[10px] uppercase opacity-80">Level</dt>
            <dd className="font-semibold">
              {card.level.number} · {card.level.name}
            </dd>
          </div>
          <div className="rounded-xl bg-white/15 p-2">
            <dt className="text-[10px] uppercase opacity-80">Profile</dt>
            <dd className="font-semibold">{card.profile_strength ?? "—"}/100</dd>
          </div>
          <div className="rounded-xl bg-white/15 p-2">
            <dt className="text-[10px] uppercase opacity-80">Streak</dt>
            <dd className="font-semibold">{card.streak_days}🔥</dd>
          </div>
        </dl>
        {card.badges.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {card.badges.map((b) => (
              <span key={b.name} className="rounded-full bg-white/15 px-2.5 py-1 text-xs">
                {b.icon} {b.name}
              </span>
            ))}
          </div>
        )}
      </article>
      <Link href={`/?ref=${card.code}`} className="rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700">
        Plan your own study-abroad journey · join with {card.first_name}&apos;s invite
      </Link>
    </main>
  );
}
