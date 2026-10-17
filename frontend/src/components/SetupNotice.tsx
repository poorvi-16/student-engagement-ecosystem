export function SetupNotice() {
  return (
    <div className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      Supabase is not configured. Add <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
      <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to <code>frontend/.env.local</code> and restart <code>npm run dev</code>.
    </div>
  );
}
