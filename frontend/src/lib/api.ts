import { supabase } from "@/lib/supabase";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } };
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(await authHeader()),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: "student" | "admin";
  referral_code: string;
  xp: number;
  streak_days: number;
};

export type StudentProfile = Record<string, unknown> & {
  profile_strength: number;
  journey_stage: string;
};

export type Me = { user: User; profile: StudentProfile | null };
