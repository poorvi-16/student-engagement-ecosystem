"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, API_URL, ApiError } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useMe } from "@/lib/useMe";

type Section = Record<string, string | number | null | undefined>;
type Check = { level: "ok" | "warn" | "error"; message: string };
type Doc = { id: number; doc_type: string; filename: string; status: string; stored: boolean; extracted: Record<string, unknown> };
type ChecklistItem = { doc_type: string; label: string; required: boolean; note: string; uploaded: boolean };
type Stage = { key: string; label: string; due_at: string; note: string; done: boolean };
type Bureau = { score: number | null; band: string; factors: string[]; report_id: string };

type App = {
  id: number;
  status: "draft" | "submitted";
  product: { id: string; lender: string; name: string; type: string; processing_fee_pct: number };
  course_id: number;
  program: { university: string; program: string; country: string };
  amount_lakhs: number;
  applicant: Section;
  co_applicant: Section;
  academics: Section;
  collateral: Section;
  checklist: ChecklistItem[];
  documents: Doc[];
  missing: string[];
  checks: Check[];
  offer: { eligible: boolean; amount_lakhs: number; rate_pct: number; apr_pct: number; emi_lakhs: number; reasons: string[]; max_amount_lakhs: number };
  secured: boolean;
  storage: boolean;
  tracker?: {
    reference: string;
    lender: string;
    stage: string;
    finished: boolean;
    timeline: Stage[];
    decision: {
      outcome: "sanctioned" | "revised" | "declined";
      amount_lakhs: number;
      rate_pct: number | null;
      tenure_years: number;
      moratorium_months: number;
      emi_lakhs: number | null;
      processing_fee_pct: number;
      reasons: string[];
      conditions: string[];
    } | null;
  };
  cibil?: { co_applicant: Bureau; student: Bureau; type: string };
};

const rupees = (l: number) => `₹${Math.round(l * 1e5).toLocaleString("en-IN")}`;
const inputCls = "w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm dark:border-gray-700";

const FIELDS: Record<string, [string, string, string?][]> = {
  applicant: [
    ["full_name", "Full name (as on PAN)"],
    ["dob", "Date of birth", "date"],
    ["pan", "PAN"],
    ["aadhaar_last4", "Aadhaar — last 4 digits only"],
    ["mobile", "Mobile number", "tel"],
    ["address", "Address"],
    ["pincode", "PIN code"],
    ["passport_expiry", "Passport expiry (if you have one)", "date"],
  ],
  co_applicant: [
    ["name", "Co-applicant name"],
    ["relation", "Relation (e.g. Father)"],
    ["pan", "Co-applicant PAN"],
    ["occupation", "Occupation (Salaried / Self-employed)"],
    ["employer", "Employer / business"],
    ["monthly_income", "Gross monthly income (₹)", "number"],
    ["existing_emi", "Existing EMIs (₹ / month)", "number"],
  ],
  collateral: [
    ["type", "Collateral type (e.g. Residential property, FD)"],
    ["value_lakhs", "Market value (₹ lakh)", "number"],
    ["address", "Property address"],
    ["owner_name", "Owner name"],
  ],
};

const STEPS = ["Loan", "You", "Co-applicant", "Collateral", "Documents", "Review"] as const;

function Tracker({ app }: { app: App }) {
  const t = app.tracker!;
  const d = t.decision;
  return (
    <div className="space-y-5">
      <section className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Application status</h2>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs dark:bg-gray-900">Ref {t.reference}</span>
        </div>
        <ol className="space-y-3">
          {t.timeline.map((s) => {
            const current = !s.done && s.key === t.stage;
            return (
              <li key={s.key} className="flex gap-3">
                <span
                  className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${s.done ? "bg-emerald-500 text-white" : current ? "animate-pulse bg-indigo-500 text-white" : "bg-gray-200 text-gray-500 dark:bg-gray-800"}`}
                >
                  {s.done ? "✓" : "•"}
                </span>
                <div>
                  <p className={`text-sm font-medium ${s.done || current ? "" : "text-gray-500"}`}>
                    {s.label}
                    {current && <span className="ml-2 text-xs font-normal text-indigo-600">in progress</span>}
                  </p>
                  {s.note && <p className="text-xs text-gray-600 dark:text-gray-400">{s.note}</p>}
                </div>
              </li>
            );
          })}
        </ol>
        {!t.finished && <p className="text-xs text-gray-500">Simulated lender: each stage takes a minute or two. This page refreshes itself.</p>}
      </section>

      {d && (
        <section
          className={`space-y-2 rounded-xl p-4 sm:p-5 ${d.outcome === "declined" ? "bg-rose-50 text-rose-950 dark:bg-rose-950 dark:text-rose-100" : "bg-emerald-50 text-emerald-950 dark:bg-emerald-950 dark:text-emerald-100"}`}
        >
          <p className="text-xs font-semibold uppercase tracking-wide">
            {d.outcome === "declined" ? "Not sanctioned" : "Provisional sanction letter (simulated)"}
          </p>
          {d.outcome !== "declined" ? (
            <>
              <p className="text-2xl font-bold">₹{d.amount_lakhs}L at {d.rate_pct}%</p>
              <p className="text-sm">
                {d.tenure_years}-year tenure after a {d.moratorium_months}-month moratorium
                {d.emi_lakhs ? ` · EMI about ${rupees(d.emi_lakhs)}` : ""} · processing fee {d.processing_fee_pct}%
              </p>
              {d.reasons.length > 0 && <p className="text-sm">{d.reasons.join(" ")}</p>}
              <ul className="list-disc pl-5 text-xs">
                {d.conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </>
          ) : (
            <ul className="list-disc pl-5 text-sm">
              {d.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          <p className="text-[11px] opacity-80">
            Prototype only: lenders are fictional and this is not an offer of credit. Real sanctions follow a human credit review.
          </p>
        </section>
      )}

      {app.cibil && t.timeline.find((s) => s.key === "bureau")?.done && (
        <section className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["Co-applicant", app.cibil.co_applicant],
              ["You", app.cibil.student],
            ] as const
          ).map(([who, b]) => (
            <div key={who} className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
              <p className="text-xs uppercase tracking-wide text-gray-500">{who} · mock bureau</p>
              <p className="text-2xl font-bold">{b.score ?? "NH"}</p>
              <p className="text-sm">{b.band}</p>
              <p className="text-xs text-gray-600 dark:text-gray-400">{b.factors.join(" · ")}</p>
            </div>
          ))}
          <p className="text-[11px] text-gray-500 sm:col-span-2">{app.cibil.type}. Scores are generated for the demo, not from a real bureau.</p>
        </section>
      )}
    </div>
  );
}

export default function ApplyPage() {
  const { me, loading } = useMe();
  const [app, setApp] = useState<App | null>(null);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Record<string, Section>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [consent, setConsent] = useState({ kyc: false, bureau: false, dpdp: false });

  const load = useCallback((a: App) => {
    setApp(a);
    setDraft({ applicant: { ...a.applicant }, co_applicant: { ...a.co_applicant }, collateral: { ...a.collateral } });
  }, []);

  useEffect(() => {
    if (!me?.profile) return;
    const q = new URLSearchParams(window.location.search);
    const product = q.get("product");
    const id = q.get("id");
    const req = product
      ? api<App>("/loan/applications", { method: "POST", body: JSON.stringify({ product_id: product, course_id: q.get("course") ? Number(q.get("course")) : null }) })
      : id
        ? api<App>(`/loan/applications/${id}`)
        : api<{ applications: { id: number }[] }>("/loan/applications").then((r) =>
            r.applications.length ? api<App>(`/loan/applications/${r.applications[0].id}`) : Promise.reject(new ApiError(404, "No application yet. Pick an offer in the loan planner first.")),
          );
    req.then(load).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me?.profile, load]);

  // Poll the tracker while the simulated lender is working
  useEffect(() => {
    if (!app?.tracker || app.tracker.finished) return;
    const t = setInterval(() => api<App>(`/loan/applications/${app.id}`).then(setApp).catch(() => {}), 15000);
    return () => clearInterval(t);
  }, [app?.id, app?.tracker?.finished, app?.tracker]);

  async function save(next?: number) {
    if (!app) return;
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = {};
      for (const s of ["applicant", "co_applicant", "collateral"]) body[s] = draft[s];
      load(await api<App>(`/loan/applications/${app.id}`, { method: "PATCH", body: JSON.stringify(body) }));
      if (next !== undefined) setStep(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function upload(docType: string, file: File) {
    if (!app) return;
    setBusy(true);
    setError("");
    try {
      await save();
      const fd = new FormData();
      fd.append("doc_type", docType);
      fd.append("file", file);
      const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } };
      const res = await fetch(`${API_URL}/loan/applications/${app.id}/documents`, {
        method: "POST",
        body: fd,
        headers: data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {},
      });
      const j = await res.json();
      if (!res.ok) throw new ApiError(res.status, typeof j.detail === "string" ? j.detail : "Upload failed");
      load(j.application);
      setToast(j.filled.length ? `✨ Auto-filled ${j.filled.length} field(s) from your document` : j.notice || "Uploaded");
      setTimeout(() => setToast(""), 3500);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeDoc(id: number) {
    if (!app) return;
    load(await api<App>(`/loan/applications/${app.id}/documents/${id}`, { method: "DELETE" }));
  }

  async function view(id: number) {
    if (!app) return;
    const r = await api<{ url: string }>(`/loan/applications/${app.id}/documents/${id}/url`);
    window.open(r.url, "_blank", "noopener");
  }

  async function submit() {
    if (!app) return;
    setBusy(true);
    setError("");
    try {
      await save();
      load(
        await api<App>(`/loan/applications/${app.id}/submit`, {
          method: "POST",
          body: JSON.stringify({ consent_kyc: consent.kyc, consent_bureau: consent.bureau, consent_dpdp: consent.dpdp }),
        }),
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;

  const steps = STEPS.filter((s) => s !== "Collateral" || app?.secured);
  const current = steps[Math.min(step, steps.length - 1)];

  function form(section: "applicant" | "co_applicant" | "collateral") {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS[section].map(([key, label, type]) => (
          <label key={key} className="space-y-1 text-sm">
            <span className="font-medium">{label}</span>
            <input
              type={type ?? "text"}
              value={(draft[section]?.[key] as string | number | undefined) ?? ""}
              maxLength={key === "aadhaar_last4" ? 4 : 160}
              onChange={(e) => setDraft((d) => ({ ...d, [section]: { ...d[section], [key]: type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value } }))}
              className={inputCls}
            />
          </label>
        ))}
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-5xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/loan" className="text-sm text-gray-500 hover:underline">
          ← Loan planner
        </Link>
        <h1 className="text-2xl font-bold">{app?.status === "submitted" ? "Loan application tracker" : "Loan application copilot"}</h1>
        {app && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {app.product.name} · {app.product.lender} · {app.program.program}, {app.program.university}
          </p>
        )}
        <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          🧪 Simulated lender, credit bureau and loan system for this prototype. Don&apos;t upload real documents if you&apos;re only testing.
        </p>
      </header>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
      {!app && !error && <p className="text-gray-500">Preparing your application…</p>}

      {app?.status === "submitted" && <Tracker app={app} />}

      {app?.status === "draft" && (
        <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
          <div className="space-y-4">
            <nav className="flex gap-1 overflow-x-auto pb-1 text-sm">
              {steps.map((s, i) => (
                <button
                  key={s}
                  onClick={() => save(i)}
                  className={`shrink-0 rounded-full px-3 py-1 ${s === current ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-400"}`}
                >
                  {i + 1}. {s}
                </button>
              ))}
            </nav>

            <section className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 sm:p-5">
              {current === "Loan" && (
                <div className="space-y-3 text-sm">
                  <p>
                    Applying for <b>₹{app.amount_lakhs}L</b> with {app.product.lender} for {app.program.program} at {app.program.university}.
                  </p>
                  <p className="text-gray-600 dark:text-gray-400">
                    We pre-filled what we know from your profile. Upload documents and the copilot reads them to fill the rest.
                  </p>
                  <Link href="/loan" className="text-indigo-600 hover:underline">
                    Change lender or amount →
                  </Link>
                </div>
              )}
              {current === "You" && form("applicant")}
              {current === "Co-applicant" && form("co_applicant")}
              {current === "Collateral" && form("collateral")}
              {current === "Documents" && (
                <ul className="space-y-2">
                  {app.checklist.map((item) => {
                    const doc = [...app.documents].reverse().find((d) => d.doc_type === item.doc_type);
                    return (
                      <li key={item.doc_type} className="space-y-1.5 rounded-lg border border-gray-200 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-medium">
                            {doc ? "✅" : item.required ? "⬜" : "▫️"} {item.label}
                            {item.required && <span className="ml-1 text-xs text-rose-600">required</span>}
                          </p>
                          <label className="cursor-pointer rounded-lg border border-indigo-300 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950">
                            {doc ? "Replace" : "Upload"}
                            <input
                              type="file"
                              accept="image/jpeg,image/png,image/webp,application/pdf"
                              className="hidden"
                              disabled={busy}
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) upload(item.doc_type, f);
                                e.target.value = "";
                              }}
                            />
                          </label>
                        </div>
                        {item.note && <p className="text-xs text-gray-500">{item.note}</p>}
                        {doc && (
                          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                            <span>{doc.filename}</span>
                            <span>· {doc.status === "extracted" ? `read ${Object.keys(doc.extracted).length} fields` : "typed manually"}</span>
                            {doc.stored && (
                              <button onClick={() => view(doc.id)} className="text-indigo-600 hover:underline">
                                View
                              </button>
                            )}
                            <button onClick={() => removeDoc(doc.id)} className="text-rose-600 hover:underline">
                              Remove
                            </button>
                          </div>
                        )}
                      </li>
                    );
                  })}
                  <p className="text-[11px] text-gray-500">
                    Files go to a private store, are viewable only via short-lived links, and are deleted automatically after 30 days.
                    Aadhaar images are never stored; we keep only the last 4 digits.
                  </p>
                </ul>
              )}
              {current === "Review" && (
                <div className="space-y-3 text-sm">
                  {app.missing.length > 0 ? (
                    <div className="rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                      <p className="font-medium">Still needed</p>
                      <ul className="list-disc pl-5">
                        {app.missing.map((m) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="rounded-lg bg-emerald-50 p-3 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">All details and required documents are in.</p>
                  )}
                  {(
                    [
                      ["kyc", "I confirm these details are true and consent to KYC verification."],
                      ["bureau", "I and my co-applicant consent to a credit bureau check (simulated hard enquiry)."],
                      ["dpdp", "I consent to processing of this data for my loan application under the DPDP Act, 2023. Documents are deleted after 30 days."],
                    ] as const
                  ).map(([k, label]) => (
                    <label key={k} className="flex gap-2">
                      <input type="checkbox" checked={consent[k]} onChange={(e) => setConsent((c) => ({ ...c, [k]: e.target.checked }))} className="mt-0.5 accent-indigo-600" />
                      <span>{label}</span>
                    </label>
                  ))}
                  <button
                    onClick={submit}
                    disabled={busy || app.missing.length > 0 || !consent.kyc || !consent.bureau || !consent.dpdp || app.checks.some((c) => c.level === "error")}
                    className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {busy ? "Submitting…" : "Submit to lender · +100 XP"}
                  </button>
                </div>
              )}

              <div className="flex justify-between border-t border-gray-100 pt-3">
                <button onClick={() => save(Math.max(0, step - 1))} disabled={step === 0 || busy} className="text-sm text-gray-500 disabled:opacity-40">
                  ← Back
                </button>
                {step < steps.length - 1 && (
                  <button onClick={() => save(step + 1)} disabled={busy} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50">
                    {busy ? "Saving…" : "Save & continue"}
                  </button>
                )}
              </div>
            </section>
          </div>

          <aside className="space-y-3">
            <section className="space-y-2 rounded-xl bg-indigo-50 p-4 text-sm text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100">
              <p className="text-xs font-semibold uppercase tracking-wide">🤖 Copilot check</p>
              <ul className="space-y-1.5">
                {app.checks.map((c, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span>{c.level === "ok" ? "✅" : c.level === "warn" ? "⚠️" : "⛔"}</span>
                    <span>{c.message}</span>
                  </li>
                ))}
              </ul>
              {app.missing.length > 0 && <p className="text-xs opacity-80">{app.missing.length} item(s) left before you can submit.</p>}
            </section>
            <section className="space-y-1 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Indicative offer with these details</p>
              {app.offer.eligible ? (
                <>
                  <p className="text-lg font-semibold">
                    ₹{app.offer.amount_lakhs}L at {app.offer.rate_pct}%
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    APR {app.offer.apr_pct}% · EMI {rupees(app.offer.emi_lakhs)}
                  </p>
                </>
              ) : (
                <p className="text-xs text-rose-600">{app.offer.reasons.join(" ")}</p>
              )}
            </section>
          </aside>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-lg">{toast}</div>
      )}
    </main>
  );
}
