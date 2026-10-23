"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type Offer = {
  product_id: string;
  lender: string;
  name: string;
  type: "secured" | "unsecured";
  eligible: boolean;
  reasons: string[];
  conditions: string[];
  max_amount_lakhs: number;
  amount_lakhs: number;
  rate_pct: number;
  rate_breakdown: string[];
  processing_fee_lakhs: number;
  apr_pct: number;
  tenure_years: number;
  moratorium_months: number;
  emi_lakhs: number;
  total_interest_lakhs: number;
  foir_pct: number;
  emi_pct_of_salary: number;
  margin_money_lakhs: number;
};

type OffersResponse = {
  case: { amount_lakhs: number; co_applicant_income_lpa: number; collateral_value_lakhs: number; admitted: boolean };
  need: { total_cost_lakhs: number; self_fund_lakhs: number; gap_lakhs: number; expected_salary_lakhs: number };
  offers: Offer[];
  best_id: string | null;
  covered_lakhs: number;
  shortfall_lakhs: number;
  tips: string[];
  program: { course_id: number; university: string; program: string; country: string; duration_months: number };
  disclaimer: string;
  note: string;
};

type Plan = {
  emi_lakhs: number;
  study_interest_lakhs: number;
  study_interest_monthly_lakhs: number;
  repayment_starts_month: number;
  months_to_repay: number;
  months_saved: number;
  total_interest_lakhs: number;
  interest_saved_lakhs: number;
  tax_saving_80e_lakhs: number;
  emi_pct_of_salary: number | null;
  moratorium_months: number;
  years: { year: number; paid_lakhs: number; interest_lakhs: number; principal_lakhs: number; balance_lakhs: number; tax_saving_80e_lakhs: number }[];
};

type Context = {
  programs: { course_id: number; label: string; country: string }[];
  default_course_id: number | null;
  profile: { co_applicant_income_lpa: number | null; has_collateral: boolean; collateral_value_lakhs: number | null };
  note: string;
};

const lakhs = (v: number) => (Math.abs(v) >= 100 ? `₹${(v / 100).toFixed(2)} Cr` : `₹${Number(v.toFixed(2)).toLocaleString("en-IN")}L`);
const rupees = (l: number) => `₹${Math.round(l * 1e5).toLocaleString("en-IN")}`;

function useDebounced(fn: () => void, deps: unknown[], ms = 400) {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const t = setTimeout(fn, ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-gray-500">{hint}</span>}
    </label>
  );
}

const inputCls = "w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-gray-700";

function OfferCard({ o, best, chosen, onPlan }: { o: Offer; best: boolean; chosen: boolean; onPlan: () => void }) {
  return (
    <article
      className={`space-y-3 rounded-xl border p-4 ${chosen ? "border-indigo-500 ring-1 ring-indigo-500" : o.eligible ? "border-gray-200 dark:border-gray-800" : "border-dashed border-gray-300 opacity-70 dark:border-gray-700"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs text-gray-500">{o.lender}</p>
          <h3 className="font-semibold">{o.name}</h3>
        </div>
        <div className="flex flex-col items-end gap-1">
          {best && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">Best match</span>}
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] capitalize text-gray-600 dark:bg-gray-900 dark:text-gray-400">{o.type}</span>
        </div>
      </div>
      {o.eligible ? (
        <>
          <dl className="grid grid-cols-3 gap-2 text-sm">
            <div>
              <dt className="text-[11px] uppercase text-gray-500">Amount</dt>
              <dd className="font-semibold">{lakhs(o.amount_lakhs)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase text-gray-500">Rate · APR</dt>
              <dd className="font-semibold">
                {o.rate_pct}% · {o.apr_pct}%
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase text-gray-500">EMI</dt>
              <dd className="font-semibold">{rupees(o.emi_lakhs)}</dd>
            </div>
          </dl>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {o.tenure_years} yrs after a {o.moratorium_months}-month moratorium · fee {rupees(o.processing_fee_lakhs)} · FOIR {o.foir_pct}%
            {o.emi_pct_of_salary ? ` · EMI ≈ ${o.emi_pct_of_salary}% of expected salary` : ""}
          </p>
          <details className="text-xs text-gray-600 dark:text-gray-400">
            <summary className="cursor-pointer">How this rate was set</summary>
            <p className="mt-1">{o.rate_breakdown.join(" · ")}</p>
            {o.reasons.length > 0 && <p className="mt-1">{o.reasons.join(" ")}</p>}
            <p className="mt-1">Conditions: {o.conditions.join(" · ")}</p>
          </details>
          <div className="flex flex-wrap gap-2">
            <button onClick={onPlan} className="rounded-lg border border-indigo-300 px-3 py-1.5 text-sm text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950">
              Plan EMI
            </button>
            <Link
              href={`/loan/apply?product=${o.product_id}`}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Apply with copilot →
            </Link>
          </div>
        </>
      ) : (
        <ul className="list-disc space-y-0.5 pl-4 text-sm text-gray-600 dark:text-gray-400">
          {o.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function Planner({ courseId, offer }: { courseId: number; offer: Offer }) {
  const [inputs, setInputs] = useState({
    amount_lakhs: offer.amount_lakhs,
    rate_pct: offer.rate_pct,
    tenure_years: offer.tenure_years,
    pay_interest_during_study: false,
    extra_monthly_lakhs: 0,
    old_tax_regime: true,
  });
  const [plan, setPlan] = useState<Plan | null>(null);
  const set = (k: keyof typeof inputs, v: number | boolean) => setInputs((x) => ({ ...x, [k]: v }));

  function load() {
    api<Plan>("/loan/plan", { method: "POST", body: JSON.stringify({ course_id: courseId, ...inputs }) })
      .then(setPlan)
      .catch(() => {});
  }
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps
  useDebounced(load, [JSON.stringify(inputs)]);

  return (
    <section id="planner" className="space-y-4 rounded-xl border border-gray-200 p-4 sm:p-5 dark:border-gray-800">
      <h2 className="font-semibold">📅 EMI &amp; moratorium planner · {offer.name}</h2>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3 text-sm">
          {(
            [
              ["amount_lakhs", "Loan amount", 1, Math.max(offer.max_amount_lakhs, 1), 1, (v: number) => lakhs(v)],
              ["rate_pct", "Interest rate", 8, 15, 0.25, (v: number) => `${v}%`],
              ["tenure_years", "Tenure after moratorium", 3, 15, 1, (v: number) => `${v} yrs`],
              ["extra_monthly_lakhs", "Extra monthly prepayment", 0, 0.5, 0.01, (v: number) => (v ? rupees(v) : "None")],
            ] as const
          ).map(([k, label, min, max, step, fmt]) => (
            <label key={k} className="block space-y-1">
              <div className="flex justify-between">
                <span>{label}</span>
                <span className="font-semibold tabular-nums">{fmt(inputs[k] as number)}</span>
              </div>
              <input type="range" min={min} max={max} step={step} value={inputs[k] as number} onChange={(e) => set(k, Number(e.target.value))} className="w-full accent-indigo-600" />
            </label>
          ))}
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={inputs.pay_interest_during_study} onChange={(e) => set("pay_interest_during_study", e.target.checked)} className="accent-indigo-600" />
            Pay simple interest during the course (lower EMI later)
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={inputs.old_tax_regime} onChange={(e) => set("old_tax_regime", e.target.checked)} className="accent-indigo-600" />
            I&apos;ll file under the old tax regime (Section 80E applies)
          </label>
        </div>
        {plan && (
          <div className="space-y-3">
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-[11px] uppercase text-gray-500">EMI from month {plan.repayment_starts_month}</dt>
                <dd className="text-lg font-semibold">{rupees(plan.emi_lakhs)}</dd>
                {plan.emi_pct_of_salary != null && <dd className="text-[11px] text-gray-500">{plan.emi_pct_of_salary}% of expected salary</dd>}
              </div>
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-[11px] uppercase text-gray-500">During study</dt>
                <dd className="text-lg font-semibold">
                  {plan.study_interest_monthly_lakhs ? `${rupees(plan.study_interest_monthly_lakhs)}/mo` : "₹0"}
                </dd>
                <dd className="text-[11px] text-gray-500">
                  {plan.study_interest_monthly_lakhs ? "simple interest paid as you go" : `${lakhs(plan.study_interest_lakhs)} interest added to the loan`}
                </dd>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
                <dt className="text-[11px] uppercase text-gray-500">Total interest</dt>
                <dd className="text-lg font-semibold">{lakhs(plan.total_interest_lakhs)}</dd>
                {plan.months_saved > 0 && (
                  <dd className="text-[11px] text-emerald-600">
                    Prepaying saves {lakhs(plan.interest_saved_lakhs)} and {plan.months_saved} months
                  </dd>
                )}
              </div>
              <div className="rounded-lg bg-emerald-50 p-3 dark:bg-emerald-950">
                <dt className="text-[11px] uppercase text-emerald-800 dark:text-emerald-300">Sec 80E tax saving</dt>
                <dd className="text-lg font-semibold">{lakhs(plan.tax_saving_80e_lakhs)}</dd>
                <dd className="text-[11px] text-emerald-800/80 dark:text-emerald-300/80">interest deduction for 8 yrs at 31.2%</dd>
              </div>
            </dl>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={plan.years} margin={{ top: 5, right: 5, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#9ca3af33" />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" />
                  <Tooltip formatter={(v: number) => lakhs(v)} labelFormatter={(y) => `Year ${y}`} contentStyle={{ fontSize: 12 }} />
                  <Bar dataKey="principal_lakhs" name="Principal" stackId="a" fill="#4f46e5" />
                  <Bar dataKey="interest_lakhs" name="Interest" stackId="a" fill="#f59e0b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
      {plan && (
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-600 dark:text-gray-400">Year-by-year schedule</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[480px] text-right tabular-nums">
              <thead className="text-xs text-gray-500">
                <tr>
                  <th className="py-1 text-left font-medium">Year</th>
                  <th className="font-medium">Paid</th>
                  <th className="font-medium">Interest</th>
                  <th className="font-medium">Principal</th>
                  <th className="font-medium">Balance</th>
                  <th className="font-medium">80E saving</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {plan.years.map((y) => (
                  <tr key={y.year}>
                    <td className="py-1 text-left">{y.year}</td>
                    <td>{lakhs(y.paid_lakhs)}</td>
                    <td>{lakhs(y.interest_lakhs)}</td>
                    <td>{lakhs(y.principal_lakhs)}</td>
                    <td>{lakhs(y.balance_lakhs)}</td>
                    <td>{y.tax_saving_80e_lakhs ? lakhs(y.tax_saving_80e_lakhs) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

export default function LoanPage() {
  const { me, loading } = useMe();
  const [ctx, setCtx] = useState<Context | null>(null);
  const [courseId, setCourseId] = useState<number | null>(null);
  const [form, setForm] = useState({ amount: 0, income: 0, emi: 0, collateral: false, collateralValue: 0, admitted: false, save: false });
  const [data, setData] = useState<OffersResponse | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState("");
  const amountTouched = useRef(false);

  useEffect(() => {
    if (!me?.profile) return;
    api<Context>("/loan")
      .then((c) => {
        setCtx(c);
        const q = new URLSearchParams(window.location.search).get("course");
        setCourseId(q ? Number(q) : c.default_course_id);
        setForm((f) => ({
          ...f,
          income: c.profile.co_applicant_income_lpa ?? 0,
          collateral: c.profile.has_collateral,
          collateralValue: c.profile.collateral_value_lakhs ?? 0,
        }));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me?.profile]);

  function load() {
    if (!courseId) return;
    api<OffersResponse>("/loan/offers", {
      method: "POST",
      body: JSON.stringify({
        course_id: courseId,
        amount_lakhs: amountTouched.current ? form.amount : null,
        co_applicant_income_lpa: form.income,
        co_applicant_emi_monthly: form.emi,
        collateral_value_lakhs: form.collateral ? form.collateralValue : 0,
        admitted: form.admitted,
        save_to_profile: form.save,
      }),
    })
      .then((d) => {
        setData(d);
        if (!amountTouched.current) setForm((f) => ({ ...f, amount: d.case.amount_lakhs }));
        setChosen((c) => (c && d.offers.some((o) => o.product_id === c && o.eligible) ? c : d.best_id));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    amountTouched.current = false;
    load();
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps
  useDebounced(load, [JSON.stringify(form)]);

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (me && !me.profile) {
    return (
      <main className="mx-auto max-w-xl space-y-4 p-6 text-center">
        <p className="text-gray-600 dark:text-gray-400">Take the 2-minute quiz first so we can estimate your loan.</p>
        <Link href="/onboarding" className="inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white">
          Start the quiz
        </Link>
      </main>
    );
  }

  const chosenOffer = data?.offers.find((o) => o.product_id === chosen && o.eligible);

  return (
    <main className="mx-auto max-w-5xl space-y-5 p-4 sm:p-8">
      <header className="space-y-1">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="text-2xl font-bold">Education loan planner</h1>
        <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          🧪 Simulated lenders and indicative offers. {ctx?.note}
        </p>
      </header>
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}

      <section className="grid gap-4 rounded-xl border border-gray-200 p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-3 dark:border-gray-800">
        <Field label="Program">
          <select value={courseId ?? ""} onChange={(e) => setCourseId(Number(e.target.value))} className={inputCls}>
            {ctx?.programs.map((p) => (
              <option key={p.course_id} value={p.course_id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label={`Loan amount: ${lakhs(form.amount)}`}
          hint={data ? `Total cost ${lakhs(data.need.total_cost_lakhs)} − own funds ${lakhs(data.need.self_fund_lakhs)} = gap ${lakhs(data.need.gap_lakhs)}` : undefined}
        >
          <input
            type="range"
            min={1}
            max={Math.max(10, Math.ceil(data?.need.total_cost_lakhs ?? 100))}
            step={1}
            value={form.amount}
            onChange={(e) => {
              amountTouched.current = true;
              setForm((f) => ({ ...f, amount: Number(e.target.value) }));
            }}
            className="w-full accent-indigo-600"
          />
        </Field>
        <Field label="Co-applicant income (₹ lakh / year)" hint="Parent or guardian; lenders require a co-applicant.">
          <input type="number" min={0} value={form.income} onChange={(e) => setForm((f) => ({ ...f, income: Number(e.target.value) }))} className={inputCls} />
        </Field>
        <Field label="Co-applicant's existing EMIs (₹ / month)">
          <input type="number" min={0} step={1000} value={form.emi} onChange={(e) => setForm((f) => ({ ...f, emi: Number(e.target.value) }))} className={inputCls} />
        </Field>
        <Field label="Collateral (property / FD)">
          <div className="flex gap-2">
            <label className="flex items-center gap-1.5 whitespace-nowrap">
              <input type="checkbox" checked={form.collateral} onChange={(e) => setForm((f) => ({ ...f, collateral: e.target.checked }))} className="accent-indigo-600" />
              I have collateral
            </label>
            {form.collateral && (
              <input
                type="number"
                min={0}
                placeholder="Value ₹L"
                value={form.collateralValue}
                onChange={(e) => setForm((f) => ({ ...f, collateralValue: Number(e.target.value) }))}
                className={inputCls}
              />
            )}
          </div>
        </Field>
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.admitted} onChange={(e) => setForm((f) => ({ ...f, admitted: e.target.checked }))} className="accent-indigo-600" />
            I already have an admit
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.save} onChange={(e) => setForm((f) => ({ ...f, save: e.target.checked }))} className="accent-indigo-600" />
            Save income &amp; collateral to my profile
          </label>
        </div>
      </section>

      {data && (
        <>
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-indigo-50 p-4 text-sm text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100">
            <p>
              {data.best_id ? (
                <>
                  Best match covers <b>{lakhs(data.covered_lakhs)}</b> of {lakhs(data.case.amount_lakhs)}
                  {data.shortfall_lakhs > 0 && <> · shortfall {lakhs(data.shortfall_lakhs)}</>}.
                </>
              ) : (
                "No simulated lender can fund this yet. Try the tips below."
              )}
            </p>
            {data.tips.length > 0 && (
              <ul className="w-full list-disc space-y-0.5 pl-5 text-xs">
                {data.tips.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            )}
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            {[...data.offers]
              .sort((a, b) => Number(b.eligible) - Number(a.eligible) || a.apr_pct - b.apr_pct)
              .map((o) => (
                <OfferCard
                  key={o.product_id}
                  o={o}
                  best={o.product_id === data.best_id}
                  chosen={o.product_id === chosen}
                  onPlan={() => {
                    setChosen(o.product_id);
                    setTimeout(() => document.getElementById("planner")?.scrollIntoView({ behavior: "smooth" }), 50);
                  }}
                />
              ))}
          </section>

          {chosenOffer && courseId && <Planner key={`${chosenOffer.product_id}-${courseId}-${chosenOffer.amount_lakhs}`} courseId={courseId} offer={chosenOffer} />}
          <p className="text-xs text-gray-500">{data.disclaimer}</p>
        </>
      )}
    </main>
  );
}
