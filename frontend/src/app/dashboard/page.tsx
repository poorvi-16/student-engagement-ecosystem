"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { api, type Me } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function DashboardPage() {
  const router = useRouter();
  const { session, loading, authError } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!session) {
      router.replace(authError ? `/login?error=${encodeURIComponent(authError)}` : "/login");
      return;
    }
    api<Me>("/me").then(setMe).catch((e) => setError(String(e)));
  }, [session, loading, authError, router]);

  async function signOut() {
    await supabase?.auth.signOut();
    router.replace("/");
  }

  if (loading || (!me && !error)) return <main className="p-6 text-gray-500">Loading…</main>;

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
          <section className="rounded-xl border border-gray-200 p-5 dark:border-gray-800">
            <p className="text-lg">
              Welcome{me.user.full_name ? `, ${me.user.full_name}` : ""} 👋
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">{me.user.email}</p>
            <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-xs text-gray-500">XP</dt>
                <dd className="text-xl font-semibold">{me.user.xp}</dd>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-xs text-gray-500">Streak</dt>
                <dd className="text-xl font-semibold">{me.user.streak_days}🔥</dd>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-xs text-gray-500">Role</dt>
                <dd className="text-xl font-semibold capitalize">{me.user.role}</dd>
              </div>
            </dl>
            <p className="mt-4 text-sm text-gray-500">
              {me.profile ? "Profile found." : "No profile yet — the onboarding quiz comes in the next step."}
            </p>
          </section>
        )
      )}
    </main>
  );
}
