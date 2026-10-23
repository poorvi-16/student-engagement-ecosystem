"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ProfileStrength } from "@/components/ProfileStrength";
import { supabase } from "@/lib/supabase";
import { useMe } from "@/lib/useMe";

export default function DashboardPage() {
  const router = useRouter();
  const { me, error, loading } = useMe();

  async function signOut() {
    await supabase?.auth.signOut();
    router.replace("/");
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4 sm:p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">PathPilot</h1>
        <button onClick={signOut} className="text-sm text-gray-600 hover:underline dark:text-gray-400">
          Sign out
        </button>
      </header>

      {error ? (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">
          Could not reach the backend: {error}
        </p>
      ) : (
        me && (
          <>
            <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
              <div>
                <p className="text-lg">Welcome{me.user.full_name ? `, ${me.user.full_name}` : ""} 👋</p>
                <p className="text-sm text-gray-600 dark:text-gray-400">{me.user.email}</p>
              </div>
              <dl className="flex gap-3 text-center">
                <div className="rounded-lg bg-gray-50 px-4 py-2 dark:bg-gray-900">
                  <dt className="text-xs text-gray-500">XP</dt>
                  <dd className="text-xl font-semibold">{me.user.xp}</dd>
                </div>
                <div className="rounded-lg bg-gray-50 px-4 py-2 dark:bg-gray-900">
                  <dt className="text-xs text-gray-500">Streak</dt>
                  <dd className="text-xl font-semibold">{me.user.streak_days}🔥</dd>
                </div>
                {me.user.role === "admin" && (
                  <div className="rounded-lg bg-gray-50 px-4 py-2 dark:bg-gray-900">
                    <dt className="text-xs text-gray-500">Role</dt>
                    <dd className="text-xl font-semibold">Admin</dd>
                  </div>
                )}
              </dl>
            </section>

            {me.profile && me.strength ? (
              <section className="space-y-4 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
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
                  className="rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 hover:shadow-sm dark:border-gray-800"
                >
                  <p className="text-2xl">🧭</p>
                  <h2 className="mt-2 font-semibold">Career Navigator</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    AI-matched universities split into Ambitious, Target and Safe — with costs, salaries and payback.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+50 XP on first run</p>
                </Link>
                <Link
                  href="/mentor"
                  className="rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 hover:shadow-sm dark:border-gray-800"
                >
                  <p className="text-2xl">🧑‍🏫</p>
                  <h2 className="mt-2 font-semibold">AI Mentor</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Ask about visas, tests, deadlines, scholarships and loans — personalised answers with sources.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+30 XP on first chat</p>
                </Link>
                <Link
                  href="/navigator"
                  className="rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 hover:shadow-sm dark:border-gray-800"
                >
                  <p className="text-2xl">🎯</p>
                  <h2 className="mt-2 font-semibold">Admit odds &amp; ROI</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Open any program for what-if sliders on your scores, total cost, EMI, payback and an India-vs-abroad comparison.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+20 XP what-if · +20 XP ROI</p>
                </Link>
                <Link
                  href="/timeline"
                  className="rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 hover:shadow-sm dark:border-gray-800"
                >
                  <p className="text-2xl">🗓️</p>
                  <h2 className="mt-2 font-semibold">Application timeline</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Your month-by-month plan: tests, SOP, LORs, deadlines, loan and visa — tick tasks off as you go.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+40 XP for your plan · +10 XP per task</p>
                </Link>
                <Link
                  href="/sop"
                  className="rounded-xl border border-gray-200 p-5 transition hover:border-indigo-400 hover:shadow-sm dark:border-gray-800"
                >
                  <p className="text-2xl">✍️</p>
                  <h2 className="mt-2 font-semibold">SOP reviewer</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Paste your Statement of Purpose for a rubric score, the fixes that matter most and a stronger opening.
                  </p>
                  <p className="mt-2 text-xs font-medium text-amber-600">+40 XP on first review</p>
                </Link>
                <div className="rounded-xl border border-dashed border-gray-300 p-5 text-gray-500 dark:border-gray-700">
                  <p className="text-2xl">🔒</p>
                  <h2 className="mt-2 font-semibold">More tools coming</h2>
                  <p className="text-sm">Visa mock interview and the loan planner unlock next.</p>
                </div>
              </section>
            ) : (
              <section className="rounded-xl border-2 border-dashed border-indigo-300 p-6 text-center dark:border-indigo-800">
                <h2 className="text-lg font-semibold">Find out how strong your profile is</h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-gray-600 dark:text-gray-400">
                  A 2-minute quiz unlocks your Profile Strength score, university matches and funding estimates.
                </p>
                <Link
                  href="/onboarding"
                  className="mt-4 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700"
                >
                  Start the quiz · +100 XP
                </Link>
              </section>
            )}
          </>
        )
      )}
    </main>
  );
}
