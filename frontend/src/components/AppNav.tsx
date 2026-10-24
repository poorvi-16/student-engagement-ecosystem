"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { api, type Me } from "@/lib/api";

const LINKS = [
  { href: "/dashboard", label: "Home", icon: "🏠" },
  { href: "/discover", label: "Discover", icon: "📚" },
  { href: "/navigator", label: "Navigator", icon: "🧭" },
  { href: "/mentor", label: "Mentor", icon: "🧑‍🏫" },
  { href: "/timeline", label: "Timeline", icon: "🗓️" },
  { href: "/sop", label: "SOP", icon: "✍️" },
  { href: "/visa", label: "Visa", icon: "🛂" },
  { href: "/loan", label: "Loan", icon: "💰" },
];

/** Sticky top bar for signed-in students: one place to jump between every tool, with XP and the admin link. */
export function AppNav() {
  const { session } = useAuth();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!session) {
      setMe(null);
      return;
    }
    api<Me>("/me").then(setMe).catch(() => {});
  }, [session, path === "/dashboard"]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!session || path === "/" || path === "/login" || path.startsWith("/card/")) return null;

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--background)]/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-3 py-2 sm:px-6">
        <Link href="/dashboard" className="flex shrink-0 items-center gap-2 font-bold">
          <span className="gradient-brand flex h-8 w-8 items-center justify-center rounded-xl text-sm text-white">✈</span>
          <span className="hidden sm:inline">PathPilot</span>
        </Link>
        <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto" aria-label="Main">
          {LINKS.map((l) => {
            const active = path === l.href || (l.href !== "/dashboard" && path.startsWith(l.href));
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition ${
                  active ? "bg-indigo-600 text-white shadow-sm" : "text-gray-600 hover:bg-[var(--muted)] dark:text-gray-300"
                }`}
              >
                <span aria-hidden>{l.icon}</span>
                <span className={active ? "" : "hidden md:inline"}>{l.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="flex shrink-0 items-center gap-2 text-sm">
          {me && (
            <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200" title="Your XP">
              ⭐ {me.user.xp} · {me.user.streak_days}🔥
            </span>
          )}
          {me?.user.role === "admin" && (
            <Link href="/admin" className="rounded-full border border-indigo-300 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-800 dark:text-indigo-300">
              Admin
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
