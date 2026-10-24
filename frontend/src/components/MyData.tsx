"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

/** DPDP rights on the dashboard: download everything we hold, or delete the account and all of its data. */
export function MyData() {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function download() {
    setBusy("export");
    setError("");
    try {
      const data = await api<unknown>("/me/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "pathpilot-my-data.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
    setBusy("");
  }

  async function remove() {
    const typed = prompt("This permanently deletes your profile, activity, loan applications, uploaded files and sign-in. Type DELETE to confirm.");
    if (typed !== "DELETE") return;
    setBusy("delete");
    setError("");
    try {
      await api("/me", { method: "DELETE", body: JSON.stringify({ confirm: "DELETE" }) });
      await supabase?.auth.signOut();
      router.replace("/");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setBusy("");
    }
  }

  return (
    <section className="space-y-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <h2 className="font-semibold">Your data</h2>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        You control what we hold about you. See the{" "}
        <Link href="/privacy" className="text-indigo-600 hover:underline">
          privacy page
        </Link>{" "}
        for details.
      </p>
      <div className="flex flex-wrap gap-2">
        <button onClick={download} disabled={!!busy} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-60 dark:border-gray-700">
          {busy === "export" ? "Preparing…" : "Download my data"}
        </button>
        <button onClick={remove} disabled={!!busy} className="rounded-lg border border-rose-300 px-3 py-1.5 text-sm text-rose-700 disabled:opacity-60 dark:border-rose-900 dark:text-rose-300">
          {busy === "delete" ? "Deleting…" : "Delete my account"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
