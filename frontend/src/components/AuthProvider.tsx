"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

type AuthState = { session: Session | null; loading: boolean; authError: string | null };

const AuthContext = createContext<AuthState>({ session: null, loading: true, authError: null });

// Supabase reports failed/expired links as #error=...&error_description=... (or ?error=...)
function readAuthErrorFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.hash.slice(1) || window.location.search);
  const desc = params.get("error_description") ?? params.get("error");
  return desc ? desc.replace(/\+/g, " ") : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ session: null, loading: true, authError: null });

  useEffect(() => {
    const authError = readAuthErrorFromUrl();
    if (!supabase) {
      setState({ session: null, loading: false, authError });
      return;
    }
    supabase.auth.getSession().then(({ data }) => setState({ session: data.session, loading: false, authError }));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) =>
      setState((s) => ({ ...s, session, loading: false })),
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
