"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { api, type Me } from "@/lib/api";

/** Redirects to /login when signed out; otherwise loads /me. */
export function useMe() {
  const router = useRouter();
  const { session, loading, authError } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => api<Me>("/me").then(setMe).catch((e) => setError(String(e.message ?? e))), []);

  useEffect(() => {
    if (loading) return;
    if (!session) {
      router.replace(authError ? `/login?error=${encodeURIComponent(authError)}` : "/login");
      return;
    }
    reload();
  }, [session, loading, authError, router, reload]);

  return { me, setMe, error, loading: loading || (!me && !error), reload };
}
