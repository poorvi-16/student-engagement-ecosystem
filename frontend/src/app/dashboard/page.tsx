"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { GrowthPanel } from "@/components/GrowthPanel";
import { MyData } from "@/components/MyData";
import { ProfileStrength } from "@/components/ProfileStrength";
import { supabase } from "@/lib/supabase";
import { useMe } from "@/lib/useMe";

export default function DashboardPage() {
  const router = useRouter();
  const { me, error, loading, reload } = useMe();

  async function signOut() {
    await supabase?.auth.signOut();
    router.replace("/");
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4 sm:p-8">
      <div className="flex justify-end">
        <button onClick={signOut} className="text-sm text-gray-500 hover:text-indigo-600 hover:underline">
          Sign out
        </button>
      </div>

      {error ? (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">
          Could not reach the backend: {error}
        </p>
      ) : (
        me && (
          <>
            <section className="gradient-brand flex flex-wrap items-center justify-between gap-4 rounded-3xl p-6 text-white shadow-lg shadow-indigo-500/20 sm:p-8">
              <div>
                <p className="text-2xl font-bold sm:text-3xl">Welcome{me.user.full_name ? `, ${me.user.full_name.split(" ")[0]}` : ""} 👋</p>
                <p className="mt-1 text-indigo-100">
                  {me.profile ? `Targeting ${me.profile.target_countries.join(", ")} · ${me.profile.target_intake}` : "Take the 2-minute quiz to unlock your plan."}
                </p>
              </div>
              <dl className="flex gap-3 text-center">
                <div className="rounded-2xl bg-white/15 px-4 py-2 backdrop-blur">
                  <dt className="text-xs text-indigo-100">XP</dt>
                  <dd className="text-xl font-semibold">{me.user.xp}</dd>
                </div>
                <div className="rounded-2xl bg-white/15 px-4 py-2 backdrop-blur">
                  <dt className="text-xs text-indigo-100">Streak</dt>
                  <dd className="text-xl font-semibold">{me.user.streak_days}🔥</dd>
                </div>
                {me.user.role === "admin" && (
                  <Link href="/admin" className="rounded-2xl bg-white px-4 py-2 text-indigo-700">
                    <dt className="text-xs">Admin</dt>
                    <dd className="text-xl font-semibold">Console →</dd>
                  </Link>
                )}
              </dl>
            </section>

            <GrowthPanel onXp={reload} />

            {me.profile && me.strength ? (
              <section className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">Profile Strength</h2>
                  <Link href="/onboarding" className="text-sm text-indigo-600 hover:underline">
                    Edit profile
                  </Link>
                </div>
                <ProfileStrength strength={me.strength} />
                <p className="text-xs text-gray-500">
                  Targeting {me.profile.target_countries.join(", ")} · {me.profile.target_intake}
                </p>
              </section>
            ) : null}

            {me.profile ? (
              <section className="grid gap-4 sm:grid-cols-2">
                <Link
                  href="/navigator"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">🧭</span>
                  <h2 className="mt-2 font-semibold">Career Navigator</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    AI-matched universities split into Ambitious, Target and Safe — with costs, salaries and payback.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+50 XP on first run</p>
                </Link>
                <Link
                  href="/mentor"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">🧑‍🏫</span>
                  <h2 className="mt-2 font-semibold">AI Mentor</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Ask about visas, tests, deadlines, scholarships and loans — personalised answers with sources.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+30 XP on first chat</p>
                </Link>
                <Link
                  href="/navigator"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">🎯</span>
                  <h2 className="mt-2 font-semibold">Admit odds &amp; ROI</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Open any program for what-if sliders on your scores, total cost, EMI, payback and an India-vs-abroad comparison.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+20 XP what-if · +20 XP ROI</p>
                </Link>
                <Link
                  href="/timeline"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">🗓️</span>
                  <h2 className="mt-2 font-semibold">Application timeline</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Your month-by-month plan: tests, SOP, LORs, deadlines, loan and visa — tick tasks off as you go.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+40 XP for your plan · +10 XP per task</p>
                </Link>
                <Link
                  href="/sop"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">✍️</span>
                  <h2 className="mt-2 font-semibold">SOP reviewer</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Paste your Statement of Purpose for a rubric score, the fixes that matter most and a stronger opening.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+40 XP on first review</p>
                </Link>
                <Link
                  href="/visa"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">🛂</span>
                  <h2 className="mt-2 font-semibold">Visa mock interview</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Practise with an AI visa officer (US, UK, Canada, Germany, Australia) and get coached after every answer.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+50 XP on your first full interview</p>
                </Link>
                <Link
                  href="/discover"
                  className="lift rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 sm:col-span-2"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">📚</span>
                  <h2 className="mt-2 font-semibold">Discover</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Guides on visas, tests, costs and funding, picked for your interests and journey stage.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">Read 5 guides for the Bookworm badge</p>
                </Link>
                <Link
                  href="/loan"
                  className="lift rounded-2xl border-2 border-indigo-200 bg-indigo-50/60 p-5 sm:col-span-2 dark:border-indigo-900 dark:bg-indigo-950/30"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-2xl dark:bg-indigo-950/60">💰</span>
                  <h2 className="mt-2 font-semibold">Education loan planner</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Soft eligibility check (no credit score impact), offers from simulated lenders, EMI &amp; moratorium planner with Section 80E savings.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+30 XP estimate · +20 XP EMI plan</p>
                </Link>
              </section>
            ) : (
              <section className="rounded-xl border-2 border-dashed border-indigo-300 p-6 text-center dark:border-indigo-800">
                <h2 className="text-lg font-semibold">Find out how strong your profile is</h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-gray-600 dark:text-gray-400">
                  A 2-minute quiz unlocks your Profile Strength score, university matches and funding estimates.
                </p>
                <Link
                  href="/onboarding"
                  className="mt-4 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white shadow-sm hover:bg-indigo-700"
                >
                  Start the quiz · +100 XP
                </Link>
              </section>
            )}
            <MyData />
          </>
        )
      )}
    </main>
  );
}
