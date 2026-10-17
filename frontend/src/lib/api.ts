import { supabase } from "@/lib/supabase";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } };
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
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
  if (!res.ok) {
    let detail = await res.text();
    try {
      const j = JSON.parse(detail);
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
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

export type StudentProfile = {
  current_status: string;
  degree: string;
  field_of_study: string;
  graduation_year: number;
  cgpa: number;
  college_tier: number;
  work_exp_months: number;
  gre: number | null;
  gmat: number | null;
  ielts: number | null;
  toefl: number | null;
  entrance_exam: string | null;
  entrance_percentile: number | null;
  target_level: string;
  target_field: string;
  target_countries: string[];
  study_in_india: boolean;
  target_intake: string;
  career_goal: string | null;
  budget_lakhs: number | null;
  co_applicant_income_lpa: number | null;
  has_collateral: boolean;
  collateral_value_lakhs: number | null;
  profile_strength: number;
  journey_stage: string;
  consent_data_processing: boolean;
  consent_marketing: boolean;
};

export type Strength = {
  score: number;
  dimensions: { key: string; label: string; score: number; max: number }[];
  tips: string[];
};

export type Me = { user: User; profile: StudentProfile | null; strength: Strength | null };

export type CatalogMeta = {
  countries: string[];
  fields: Record<string, string>;
  university_count: number;
  course_count: number;
  disclaimer: string;
};
