"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ProfileStrength } from "@/components/ProfileStrength";
import { api, type CatalogMeta, type Me } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Form = {
  full_name: string;
  current_status: string;
  degree: string;
  field_of_study: string;
  graduation_year: string;
  college_tier: string;
  cgpa: string;
  work_exp_months: string;
  target_level: string;
  target_field: string;
  target_countries: string[];
  target_intake: string;
  career_goal: string;
  gre: string;
  gmat: string;
  ielts: string;
  toefl: string;
  entrance_exam: string;
  entrance_percentile: string;
  budget_lakhs: string;
  co_applicant_income_lpa: string;
  has_collateral: boolean;
  collateral_value_lakhs: string;
  consent_data_processing: boolean;
  consent_marketing: boolean;
};

const EMPTY: Form = {
  full_name: "",
  current_status: "",
  degree: "",
  field_of_study: "",
  graduation_year: "",
  college_tier: "",
  cgpa: "8.0",
  work_exp_months: "0",
  target_level: "",
  target_field: "",
  target_countries: [],
  target_intake: "",
  career_goal: "",
  gre: "",
  gmat: "",
  ielts: "",
  toefl: "",
  entrance_exam: "",
  entrance_percentile: "",
  budget_lakhs: "",
  co_applicant_income_lpa: "",
  has_collateral: false,
  collateral_value_lakhs: "",
  consent_data_processing: false,
  consent_marketing: false,
};

const STATUS = [
  ["ug_2nd_year", "2nd-year UG"],
  ["ug_3rd_year", "3rd-year UG"],
  ["ug_final_year", "Final-year UG"],
  ["graduate", "Graduated"],
  ["working", "Working professional"],
];
const TIERS = [
  ["1", "IIT / NIT / BITS / NIRF top-50"],
  ["2", "Well-known university or college"],
  ["3", "Other college"],
];
const LEVELS = [
  ["masters", "Master's (MS / M.Tech)"],
  ["mba", "MBA"],
  ["phd", "PhD"],
];
const DEGREES = ["B.Tech / B.E.", "B.Sc", "B.Com", "BBA", "BCA", "BA", "Other"];
const STEPS = ["About you", "Academics", "Goals", "Tests", "Finances", "Finish"];

const num = (s: string) => (s.trim() === "" ? null : Number(s));
const inputCls = "w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700";

function intakes() {
  const y = new Date().getFullYear();
  return [y, y + 1, y + 2].flatMap((yr) => [`Spring ${yr}`, `Fall ${yr}`]).slice(1, 6);
}

function Choice({ options, value, onChange }: { options: string[][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={`rounded-lg border px-3 py-2.5 text-left text-sm transition ${
            value === v
              ? "border-indigo-600 bg-indigo-50 font-medium text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100"
              : "border-gray-300 hover:border-gray-400 dark:border-gray-700"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-1.5">
      <span className="text-sm font-medium">{children}</span>
      {hint && <span className="ml-2 text-xs text-gray-500">{hint}</span>}
    </div>
  );
}

export default function OnboardingPage() {
  const { me, loading, error: loadError } = useMe();
  const [meta, setMeta] = useState<CatalogMeta | null>(null);
  const [f, setF] = useState<Form>(EMPTY);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Me | null>(null);

  useEffect(() => {
    api<CatalogMeta>("/catalog/meta").then(setMeta).catch(() => setError("Could not load options from the backend."));
  }, []);

  // Pre-fill when editing an existing profile
  useEffect(() => {
    if (!me) return;
    const p = me.profile;
    const s = (v: unknown) => (v === null || v === undefined ? "" : String(v));
    setF((prev) => ({
      ...prev,
      full_name: me.user.full_name ?? "",
      ...(p && {
        current_status: p.current_status,
        degree: p.degree,
        field_of_study: p.field_of_study,
        graduation_year: s(p.graduation_year),
        college_tier: s(p.college_tier),
        cgpa: s(p.cgpa),
        work_exp_months: s(p.work_exp_months),
        target_level: p.target_level,
        target_field: p.target_field,
        target_countries: p.target_countries,
        target_intake: p.target_intake,
        career_goal: p.career_goal ?? "",
        gre: s(p.gre),
        gmat: s(p.gmat),
        ielts: s(p.ielts),
        toefl: s(p.toefl),
        entrance_exam: p.entrance_exam ?? "",
        entrance_percentile: s(p.entrance_percentile),
        budget_lakhs: s(p.budget_lakhs),
        co_applicant_income_lpa: s(p.co_applicant_income_lpa),
        has_collateral: p.has_collateral,
        collateral_value_lakhs: s(p.collateral_value_lakhs),
        consent_data_processing: p.consent_data_processing,
        consent_marketing: p.consent_marketing,
      }),
    }));
  }, [me]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((prev) => ({ ...prev, [k]: v }));
  const abroad = f.target_countries.some((c) => c !== "India");
  const india = f.target_countries.includes("India");
  const years = useMemo(() => Array.from({ length: 10 }, (_, i) => String(new Date().getFullYear() - 5 + i)), []);

  const stepValid = [
    Boolean(f.full_name.trim() && f.current_status && f.degree && f.field_of_study.trim() && f.graduation_year && f.college_tier),
    Boolean(f.cgpa),
    Boolean(f.target_level && f.target_field && f.target_countries.length && f.target_intake),
    true,
    true,
    f.consent_data_processing,
  ][step];

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const body = {
        full_name: f.full_name.trim(),
        current_status: f.current_status,
        degree: f.degree,
        field_of_study: f.field_of_study.trim(),
        graduation_year: Number(f.graduation_year),
        college_tier: Number(f.college_tier),
        cgpa: Number(f.cgpa),
        work_exp_months: Number(f.work_exp_months || 0),
        gre: abroad ? num(f.gre) : null,
        gmat: abroad || f.entrance_exam === "GMAT" ? num(f.gmat) : null,
        ielts: abroad ? num(f.ielts) : null,
        toefl: abroad ? num(f.toefl) : null,
        entrance_exam: india && f.entrance_exam ? f.entrance_exam : null,
        entrance_percentile: india ? num(f.entrance_percentile) : null,
        target_level: f.target_level,
        target_field: f.target_field,
        target_countries: f.target_countries,
        target_intake: f.target_intake,
        career_goal: f.career_goal.trim() || null,
        budget_lakhs: num(f.budget_lakhs),
        co_applicant_income_lpa: num(f.co_applicant_income_lpa),
        has_collateral: f.has_collateral,
        collateral_value_lakhs: f.has_collateral ? num(f.collateral_value_lakhs) : null,
        consent_data_processing: f.consent_data_processing,
        consent_marketing: f.consent_marketing,
      };
      setResult(await api<Me>("/me/profile", { method: "PUT", body: JSON.stringify(body) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (loadError) return <main className="p-6 text-red-600">Could not reach the backend: {loadError}</main>;

  if (result?.strength) {
    const firstTime = !me?.profile;
    return (
      <main className="mx-auto max-w-xl space-y-6 p-4 sm:p-8">
        <div className="text-center">
          {firstTime && (
            <span className="inline-block rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-800 dark:bg-amber-900 dark:text-amber-100">
              +100 XP · Profile created 🎉
            </span>
          )}
          <h1 className="mt-3 text-2xl font-bold">Your Profile Strength</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            How ready your profile is for {f.target_countries.join(", ")}. Every tip you act on raises it.
          </p>
        </div>
        <section className="rounded-xl border border-gray-200 p-5 dark:border-gray-800">
          <ProfileStrength strength={result.strength} />
        </section>
        <Link href="/dashboard" className="block rounded-lg bg-indigo-600 px-4 py-2.5 text-center font-medium text-white hover:bg-indigo-700">
          Go to my dashboard
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl space-y-6 p-4 sm:p-8">
      <header className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <Link href="/dashboard" className="text-gray-500 hover:underline">
            ← Dashboard
          </Link>
          <span className="text-gray-500">
            Step {step + 1} of {STEPS.length}
          </span>
        </div>
        <div className="flex gap-1">
          {STEPS.map((s, i) => (
            <div key={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-indigo-600" : "bg-gray-200 dark:bg-gray-800"}`} />
          ))}
        </div>
        <h1 className="text-2xl font-bold">{STEPS[step]}</h1>
      </header>

      <section className="space-y-5">
        {step === 0 && (
          <>
            <div>
              <Label>Your name</Label>
              <input value={f.full_name} onChange={(e) => set("full_name", e.target.value)} className={inputCls} />
            </div>
            <div>
              <Label>Where are you right now?</Label>
              <Choice options={STATUS} value={f.current_status} onChange={(v) => set("current_status", v)} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label>Degree</Label>
                <select value={f.degree} onChange={(e) => set("degree", e.target.value)} className={inputCls}>
                  <option value="">Select…</option>
                  {DEGREES.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Graduation year</Label>
                <select value={f.graduation_year} onChange={(e) => set("graduation_year", e.target.value)} className={inputCls}>
                  <option value="">Select…</option>
                  {years.map((y) => (
                    <option key={y}>{y}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <Label>Branch / major</Label>
              <input
                value={f.field_of_study}
                onChange={(e) => set("field_of_study", e.target.value)}
                placeholder="e.g. Computer Science"
                className={inputCls}
              />
            </div>
            <div>
              <Label>Your college</Label>
              <Choice options={TIERS} value={f.college_tier} onChange={(v) => set("college_tier", v)} />
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <div>
              <Label hint="on a 10-point scale">CGPA: {Number(f.cgpa).toFixed(1)}</Label>
              <input
                type="range"
                min={5}
                max={10}
                step={0.1}
                value={f.cgpa}
                onChange={(e) => set("cgpa", e.target.value)}
                className="w-full accent-indigo-600"
              />
            </div>
            <div>
              <Label hint="internships count too">
                Work experience: {f.work_exp_months} month{f.work_exp_months === "1" ? "" : "s"}
              </Label>
              <input
                type="range"
                min={0}
                max={96}
                step={1}
                value={f.work_exp_months}
                onChange={(e) => set("work_exp_months", e.target.value)}
                className="w-full accent-indigo-600"
              />
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <Label>What do you want to study?</Label>
              <Choice options={LEVELS} value={f.target_level} onChange={(v) => set("target_level", v)} />
            </div>
            <div>
              <Label>Field</Label>
              <select value={f.target_field} onChange={(e) => set("target_field", e.target.value)} className={inputCls}>
                <option value="">Select…</option>
                {meta &&
                  Object.entries(meta.fields).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <Label hint="pick one or more">Where?</Label>
              <div className="flex flex-wrap gap-2">
                {meta?.countries.map((c) => {
                  const on = f.target_countries.includes(c);
                  return (
                    <button
                      key={c}
                      type="button"
                      onClick={() => set("target_countries", on ? f.target_countries.filter((x) => x !== c) : [...f.target_countries, c])}
                      className={`rounded-full border px-3 py-1.5 text-sm ${
                        on ? "border-indigo-600 bg-indigo-600 text-white" : "border-gray-300 dark:border-gray-700"
                      }`}
                    >
                      {c}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <Label>Target intake</Label>
              <select value={f.target_intake} onChange={(e) => set("target_intake", e.target.value)} className={inputCls}>
                <option value="">Select…</option>
                {intakes().map((i) => (
                  <option key={i}>{i}</option>
                ))}
              </select>
            </div>
            <div>
              <Label hint="optional">Dream role after graduation</Label>
              <input
                value={f.career_goal}
                onChange={(e) => set("career_goal", e.target.value)}
                placeholder="e.g. ML engineer at a product company"
                className={inputCls}
              />
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <p className="text-sm text-gray-600 dark:text-gray-400">Leave blank anything you haven&apos;t taken yet. We&apos;ll tell you what matters most.</p>
            {abroad && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label hint="260–340">GRE</Label>
                  <input type="number" min={260} max={340} value={f.gre} onChange={(e) => set("gre", e.target.value)} className={inputCls} />
                </div>
                <div>
                  <Label hint="200–805">GMAT</Label>
                  <input type="number" min={200} max={805} value={f.gmat} onChange={(e) => set("gmat", e.target.value)} className={inputCls} />
                </div>
                <div>
                  <Label hint="0–9">IELTS</Label>
                  <input type="number" min={0} max={9} step={0.5} value={f.ielts} onChange={(e) => set("ielts", e.target.value)} className={inputCls} />
                </div>
                <div>
                  <Label hint="0–120">TOEFL</Label>
                  <input type="number" min={0} max={120} value={f.toefl} onChange={(e) => set("toefl", e.target.value)} className={inputCls} />
                </div>
              </div>
            )}
            {india && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label>Indian entrance exam</Label>
                  <select value={f.entrance_exam} onChange={(e) => set("entrance_exam", e.target.value)} className={inputCls}>
                    <option value="">Not taken yet</option>
                    <option>CAT</option>
                    <option>GATE</option>
                    <option>GMAT</option>
                  </select>
                </div>
                <div>
                  <Label hint="0–100">Percentile</Label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.01}
                    value={f.entrance_percentile}
                    onChange={(e) => set("entrance_percentile", e.target.value)}
                    disabled={!f.entrance_exam}
                    className={`${inputCls} disabled:opacity-50`}
                  />
                </div>
              </div>
            )}
          </>
        )}

        {step === 4 && (
          <>
            <p className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100">
              Why we ask: to estimate how much funding you&apos;ll need and which education loans fit. No credit check, nothing is shared.
            </p>
            <div>
              <Label hint="₹ lakhs">How much can your family self-fund?</Label>
              <input type="number" min={0} value={f.budget_lakhs} onChange={(e) => set("budget_lakhs", e.target.value)} placeholder="e.g. 10" className={inputCls} />
            </div>
            <div>
              <Label hint="₹ lakhs per year, usually a parent">Co-applicant&apos;s annual income</Label>
              <input
                type="number"
                min={0}
                value={f.co_applicant_income_lpa}
                onChange={(e) => set("co_applicant_income_lpa", e.target.value)}
                placeholder="e.g. 12"
                className={inputCls}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.has_collateral} onChange={(e) => set("has_collateral", e.target.checked)} className="h-4 w-4 accent-indigo-600" />
              We can offer collateral (property, FD, etc.)
            </label>
            {f.has_collateral && (
              <div>
                <Label hint="₹ lakhs, approximate">Collateral value</Label>
                <input
                  type="number"
                  min={0}
                  value={f.collateral_value_lakhs}
                  onChange={(e) => set("collateral_value_lakhs", e.target.value)}
                  className={inputCls}
                />
              </div>
            )}
          </>
        )}

        {step === 5 && (
          <div className="space-y-3 text-sm">
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={f.consent_data_processing}
                onChange={(e) => set("consent_data_processing", e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-indigo-600"
              />
              <span>
                I agree that PathPilot can process my details to personalise recommendations and show indicative loan options.{" "}
                <span className="text-gray-500">(Required)</span>
              </span>
            </label>
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={f.consent_marketing}
                onChange={(e) => set("consent_marketing", e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-indigo-600"
              />
              <span>Send me deadline reminders and tips. (Optional)</span>
            </label>
            {meta && <p className="text-xs text-gray-500">{meta.disclaimer}</p>}
          </div>
        )}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <footer className="flex justify-between gap-3">
        <button
          type="button"
          onClick={() => setStep((s) => s - 1)}
          disabled={step === 0}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm disabled:invisible dark:border-gray-700"
        >
          Back
        </button>
        {step < STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            disabled={!stepValid}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Next
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!stepValid || busy}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Calculating…" : "See my Profile Strength"}
          </button>
        )}
      </footer>
    </main>
  );
}
