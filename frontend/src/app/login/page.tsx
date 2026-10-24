"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { SetupNotice } from "@/components/SetupNotice";
import { supabase } from "@/lib/supabase";

type Mode = "signin" | "signup" | "magic";

const inputCls = "w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700";
const primaryBtn =
  "w-full rounded-lg bg-indigo-600 px-3 py-2 font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60";

export default function LoginPage() {
  const router = useRouter();
  const { session, authError } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(authError ? `Sign-in link problem: ${authError}` : "");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (session) router.replace("/dashboard");
  }, [session, router]);

  const redirectTo = typeof window !== "undefined" ? `${window.location.origin}/dashboard` : undefined;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError("");
    setNotice("");

    if (mode === "signin") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) setError(error.message);
    } else if (mode === "signup") {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: fullName }, emailRedirectTo: redirectTo },
      });
      if (error) setError(error.message);
      else if (!data.session) setNotice(`Account created. Confirm it from the email sent to ${email}, then sign in.`);
    } else {
      const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo } });
      if (error) setError(error.message);
      else setNotice(`Check ${email} for a sign-in link.`);
    }
    setBusy(false);
  }

  async function signInWithGoogle() {
    await supabase?.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
  }

  const tabs: { id: Mode; label: string }[] = [
    { id: "signin", label: "Sign in" },
    { id: "signup", label: "Create account" },
    { id: "magic", label: "Email link" },
  ];

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6 rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6 shadow-xl shadow-indigo-500/10 sm:p-8">
        <div className="text-center">
          <span className="gradient-brand mx-auto flex h-12 w-12 items-center justify-center rounded-2xl text-xl text-white">✈</span>
          <h1 className="mt-3 text-2xl font-bold">Welcome to PathPilot</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">Sign in to start your journey</p>
        </div>

        {!supabase ? (
          <SetupNotice />
        ) : (
          <>
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-gray-100 p-1 text-sm dark:bg-gray-900">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    setMode(t.id);
                    setError("");
                    setNotice("");
                  }}
                  className={`rounded-md px-2 py-1.5 ${mode === t.id ? "bg-white font-medium shadow-sm dark:bg-gray-800" : "text-gray-600 dark:text-gray-400"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="space-y-3">
              {mode === "signup" && (
                <input required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" className={inputCls} />
              )}
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@college.edu"
                autoComplete="email"
                className={inputCls}
              />
              {mode !== "magic" && (
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password (min 6 characters)"
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  className={inputCls}
                />
              )}
              <button disabled={busy} className={primaryBtn}>
                {busy ? "Please wait…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Email me a sign-in link"}
              </button>
              {error && <p className="text-sm text-red-600">{error}</p>}
              {notice && (
                <p className="rounded-lg bg-green-50 p-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-200">{notice}</p>
              )}
            </form>

            <div className="text-center text-xs text-gray-500">or</div>
            <button
              onClick={signInWithGoogle}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-medium hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
            >
              Continue with Google
            </button>
          </>
        )}
      </div>
    </main>
  );
}
