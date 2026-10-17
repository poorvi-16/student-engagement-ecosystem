import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const supabaseConfigured = Boolean(url && anonKey);

// Null when env vars are missing so pages can show a setup message instead of crashing.
export const supabase: SupabaseClient | null = supabaseConfigured ? createClient(url, anonKey) : null;
