"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/useMe";

type ScoreKey = "cgpa" | "gre" | "gmat" | "ielts" | "toefl" | "entrance_percentile" | "work_exp_months";
type Scores = Partial<Record<ScoreKey, number | null>>;

type Admit = {
  chance: number;
  bucket: "ambitious" | "target" | "safe";
  baseline_chance?: number;
  factors: { factor: string; yours: string; typical: string; impact_pct: number }[];
  levers: { label: string; changes: Scores; chance: number; delta_pct: number }[];
  typical_admit: {
    cgpa: number;
    test_kind: "gre" | "gmat" | "entrance" | null;
    test: number | null;
    ielts_min: number | null;
    ielts: number | null;
    work_exp_months: number;
  };
  acceptance_rate: number;
};

type Roi = {
  cost: {
    tuition_lakhs: number;
    living_lakhs: number;
    fx_buffer_lakhs: number;
    one_time_lakhs: number;
    scholarship_lakhs: number;
    total_lakhs: number;
    duration_months: number;
  };
  funding: { self_fund_lakhs: number; gap_lakhs: number };
  loan: {
    principal_lakhs: number;
    rate_pct: number;
    moratorium_months: number;
    moratorium_interest_lakhs: number;
    emi_lakhs: number;
    tenure_years: number;
    total_interest_lakhs: number;
    emi_pct_of_salary: number;
  };
  salary: { start_lakhs: number; location: string; program_median_lakhs: number };
  outcome: { payback_years: number | null; ten_year_savings_lakhs: number; ten_year_net_lakhs: number; roi_multiple: number | null };
  series: { year: number; net_lakhs: number; salary_lakhs: number }[];
};

type Program = {
  course_id: number;
  university: string;
  country: string;
  city: string;
  tier: number;
  qs_rank: number | null;
  program: string;
  level: string;
  duration_months: number;
  stem: boolean;
  deadline_month: number;
  acceptance_rate: number;
  entrance_exam: string | null;
};

type Alternative = { program: Program; chance: number; roi: Roi } | null;

type Detail = {
  program: Program;
  admit: Admit;
  roi: Roi;
  alternative: Alternative;
  profile: Scores & { budget_lakhs: number | null };
  shortlisted: boolean;
  model: { kind: "ml" | "heuristic"; algorithm?: string; trained_rows?: number; auc?: number };
  roi_note: string;
  disclaimer: string;
};

type RoiInputs = {
  scholarship_lakhs: number;
  living_style: "frugal" | "standard" | "comfortable";
  inr_depreciation_pct: number;
  salary_adjust_pct: number;
  work_in: "abroad" | "india";
  savings_rate_pct: number;
  loan_rate_pct: number;
  self_fund_lakhs: number;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const BUCKET_STYLE = {
  ambitious: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  target: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
  safe: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
};

const lakhs = (v: number) => (Math.abs(v) >= 100 ? `₹${(v / 100).toFixed(2)} Cr` : `₹${v.toLocaleString("en-IN")}L`);
const rupees = (l: number) => `₹${Math.round(l * 1e5).toLocaleString("en-IN")}`;
const pct = (p: number) => `${Math.round(p * 100)}%`;
const payback = (y: number | null) => (y == null ? "10+ yrs" : `${y} yrs`);

/** Calls `fn` `ms` after the last change of `deps`, skipping the first render. */
function useDebounced(fn: () => void, deps: unknown[], ms = 350) {
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

function Card({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-xl border border-gray-200 p-4 sm:p-5 dark:border-gray-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  hint?: string;
  onChange: (v: number) => void;
}) {
  const f = props.format ?? String;
  return (
    <label className="block space-y-1">
      <div className="flex justify-between text-sm">
        <span>{props.label}</span>
        <span className="font-semibold tabular-nums">{f(props.value)}</span>
      </div>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
        className="w-full accent-indigo-600"
      />
      {props.hint && <p className="text-[11px] text-gray-500">{props.hint}</p>}
    </label>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
      <dt className="text-[11px] uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
      {sub && <dd className="text-[11px] text-gray-500">{sub}</dd>}
    </div>
  );
}

// ---------- admit predictor ----------

function AdmitPanel({ courseId, detail }: { courseId: string; detail: Detail }) {
  const t = detail.admit.typical_admit;
  const testKey: ScoreKey | null = t.test_kind === "entrance" ? "entrance_percentile" : t.test_kind;
  const abroad = detail.program.country !== "India";
  const englishKey: ScoreKey = detail.profile.ielts == null && detail.profile.toefl != null ? "toefl" : "ielts";
  const keys = (["cgpa", testKey, abroad && t.ielts ? englishKey : null, "work_exp_months"] as const).filter(Boolean) as ScoreKey[];

  const initial: Scores = Object.fromEntries(keys.map((k) => [k, detail.profile[k] ?? null]));
  const [scores, setScores] = useState<Scores>(initial);
  const [view, setView] = useState<Admit>(detail.admit);
  const [busy, setBusy] = useState(false);

  const overrides = Object.fromEntries(
    Object.entries(scores).filter(([k, v]) => v != null && v !== detail.profile[k as ScoreKey]),
  ) as Scores;
  const changed = Object.keys(overrides).length > 0;

  useDebounced(() => {
    setBusy(true);
    api<Admit>(`/programs/${courseId}/admit`, { method: "POST", body: JSON.stringify(overrides) })
      .then(setView)
      .catch(() => {})
      .finally(() => setBusy(false));
  }, [JSON.stringify(overrides)]);

  const testName = t.test_kind === "entrance" ? `${detail.program.entrance_exam ?? "Entrance"} percentile` : t.test_kind?.toUpperCase();
  const spec: Record<ScoreKey, { label: string; min: number; max: number; step: number; typical?: number | null; fmt?: (v: number) => string }> = {
    cgpa: { label: "CGPA (10-pt)", min: 5, max: 10, step: 0.1, typical: t.cgpa, fmt: (v) => v.toFixed(1) },
    gre: { label: "GRE", min: 260, max: 340, step: 1, typical: t.test },
    gmat: { label: "GMAT", min: 400, max: 800, step: 10, typical: t.test },
    entrance_percentile: { label: testName ?? "Percentile", min: 50, max: 100, step: 0.5, typical: t.test },
    ielts: { label: "IELTS", min: 5, max: 9, step: 0.5, typical: t.ielts_min, fmt: (v) => v.toFixed(1) },
    toefl: { label: "TOEFL", min: 60, max: 120, step: 1 },
    work_exp_months: { label: "Work experience", min: 0, max: 120, step: 6, typical: t.work_exp_months, fmt: (v) => `${v} mo` },
  };

  const base = view.baseline_chance ?? detail.admit.chance;
  const delta = Math.round((view.chance - base) * 100);
  const maxImpact = Math.max(10, ...view.factors.map((f) => Math.abs(f.impact_pct)));

  return (
    <Card
      title="🎯 Admission odds"
      right={
        changed && (
          <button onClick={() => setScores(initial)} className="text-sm text-gray-500 hover:underline">
            Reset to my profile
          </button>
        )
      }
    >
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <p className={`text-5xl font-bold tabular-nums transition-opacity ${busy ? "opacity-50" : ""}`}>{pct(view.chance)}</p>
          <p className="text-sm text-gray-500">
            {changed ? (
              <>
                with these changes · now {pct(base)}{" "}
                <span className={delta >= 0 ? "font-semibold text-emerald-600" : "font-semibold text-rose-600"}>
                  ({delta >= 0 ? "+" : ""}
                  {delta} pts)
                </span>
              </>
            ) : (
              <>estimated chance · overall acceptance ~{pct(view.acceptance_rate)}</>
            )}
          </p>
        </div>
        <span className={`mb-2 rounded-full px-3 py-1 text-sm font-semibold capitalize ${BUCKET_STYLE[view.bucket]}`}>{view.bucket}</span>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">What-if sliders</p>
          {keys.map((k) => {
            const s = spec[k];
            const v = scores[k];
            if (v == null) {
              return (
                <button
                  key={k}
                  onClick={() => setScores((x) => ({ ...x, [k]: s.typical ?? s.min }))}
                  className="w-full rounded-lg border border-dashed border-gray-300 p-2 text-left text-sm text-gray-600 hover:border-indigo-400 dark:border-gray-700 dark:text-gray-400"
                >
                  {s.label}: not taken yet — <span className="text-indigo-600">try a score</span>
                </button>
              );
            }
            return (
              <Slider
                key={k}
                label={s.label}
                value={v}
                min={s.min}
                max={s.max}
                step={s.step}
                format={s.fmt}
                hint={s.typical != null ? `Typical admit: ${s.fmt ? s.fmt(s.typical) : s.typical}${k === "ielts" ? " minimum" : ""}` : undefined}
                onChange={(nv) => setScores((x) => ({ ...x, [k]: nv }))}
              />
            );
          })}
          {view.levers.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Biggest boosts</p>
              {view.levers.map((lv) => (
                <button
                  key={lv.label}
                  onClick={() => setScores((x) => ({ ...x, ...lv.changes }))}
                  className="flex w-full items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-left text-sm hover:bg-emerald-100 dark:bg-emerald-950/60 dark:hover:bg-emerald-950"
                >
                  <span>{lv.label}</span>
                  <span className="font-semibold text-emerald-700 dark:text-emerald-300">+{lv.delta_pct} pts</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">What drives your odds (vs a typical admit)</p>
          {view.factors.map((f) => (
            <div key={f.factor} className="space-y-1">
              <div className="flex justify-between gap-2 text-sm">
                <span>
                  {f.factor} <span className="text-gray-500">· you {f.yours} vs {f.typical}</span>
                </span>
                <span className={`shrink-0 font-semibold tabular-nums ${f.impact_pct >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                  {f.impact_pct >= 0 ? "+" : ""}
                  {f.impact_pct}
                </span>
              </div>
              <div className="flex h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                <div
                  className={f.impact_pct >= 0 ? "bg-emerald-500" : "bg-rose-500"}
                  style={{ width: `${(Math.abs(f.impact_pct) / maxImpact) * 100}%` }}
                />
              </div>
            </div>
          ))}
          <p className="pt-1 text-[11px] text-gray-500">
            Points = how much higher or lower your chance is than if that one item matched a typical admitted student.
          </p>
        </div>
      </div>
    </Card>
  );
}

// ---------- ROI ----------

function RoiPanel({ courseId, detail }: { courseId: string; detail: Detail }) {
  const abroad = detail.program.country !== "India";
  const initial: RoiInputs = {
    scholarship_lakhs: 0,
    living_style: "standard",
    inr_depreciation_pct: 3,
    salary_adjust_pct: 0,
    work_in: "abroad",
    savings_rate_pct: 35,
    loan_rate_pct: 11,
    self_fund_lakhs: detail.profile.budget_lakhs ?? 0,
  };
  const [inputs, setInputs] = useState<RoiInputs>(initial);
  const [data, setData] = useState<{ roi: Roi; alternative: Alternative }>({ roi: detail.roi, alternative: detail.alternative });
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof RoiInputs>(k: K, v: RoiInputs[K]) => setInputs((x) => ({ ...x, [k]: v }));

  useDebounced(() => {
    setBusy(true);
    api<{ roi: Roi; alternative: Alternative }>(`/programs/${courseId}/roi`, { method: "POST", body: JSON.stringify(inputs) })
      .then(setData)
      .catch(() => {})
      .finally(() => setBusy(false));
  }, [JSON.stringify(inputs)]);

  const { roi, alternative: alt } = data;
  const altLabel = alt ? `${alt.program.university.replace("Indian Institute of Technology", "IIT")}` : "";
  const chart = roi.series.map((s, i) => ({ year: `Y${s.year}`, chosen: s.net_lakhs, alt: alt?.roi.series[i]?.net_lakhs }));
  const tuitionMax = Math.max(5, Math.floor(roi.cost.tuition_lakhs));

  return (
    <Card title="💰 Return on investment" right={busy ? <span className="text-xs text-gray-500">Updating…</span> : null}>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total cost" value={lakhs(roi.cost.total_lakhs)} sub={`${roi.cost.duration_months} months, all-in`} />
        <Stat label="Funding gap" value={lakhs(roi.funding.gap_lakhs)} sub={`after ${lakhs(roi.funding.self_fund_lakhs)} own funds`} />
        <Stat
          label="Indicative EMI"
          value={roi.loan.emi_lakhs ? `${rupees(roi.loan.emi_lakhs)}/mo` : "No loan"}
          sub={roi.loan.emi_lakhs ? `${roi.loan.emi_pct_of_salary}% of starting salary` : undefined}
        />
        <Stat label="Payback" value={payback(roi.outcome.payback_years)} sub={`10-yr net ${lakhs(roi.outcome.ten_year_net_lakhs)}`} />
      </dl>

      <div className="grid gap-6 md:grid-cols-[1fr_1.2fr]">
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Your assumptions</p>
          <Slider
            label="Scholarship"
            value={inputs.scholarship_lakhs}
            min={0}
            max={tuitionMax}
            step={1}
            format={(v) => (v ? lakhs(v) : "None")}
            onChange={(v) => set("scholarship_lakhs", v)}
          />
          <Slider
            label="Own funds (family savings)"
            value={inputs.self_fund_lakhs}
            min={0}
            max={Math.max(50, Math.ceil(roi.cost.total_lakhs))}
            step={1}
            format={lakhs}
            onChange={(v) => set("self_fund_lakhs", v)}
          />
          <div className="space-y-1">
            <p className="text-sm">Lifestyle</p>
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-gray-100 p-1 text-sm dark:bg-gray-900">
              {(["frugal", "standard", "comfortable"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => set("living_style", s)}
                  className={`rounded-md py-1 capitalize ${inputs.living_style === s ? "bg-white font-medium shadow-sm dark:bg-gray-800" : "text-gray-600 dark:text-gray-400"}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          {abroad && (
            <div className="space-y-1">
              <p className="text-sm">After graduating, work in</p>
              <div className="grid grid-cols-2 gap-1 rounded-lg bg-gray-100 p-1 text-sm dark:bg-gray-900">
                {(["abroad", "india"] as const).map((w) => (
                  <button
                    key={w}
                    onClick={() => set("work_in", w)}
                    className={`rounded-md py-1 ${inputs.work_in === w ? "bg-white font-medium shadow-sm dark:bg-gray-800" : "text-gray-600 dark:text-gray-400"}`}
                  >
                    {w === "abroad" ? detail.program.country : "India"}
                  </button>
                ))}
              </div>
            </div>
          )}
          <Slider
            label="Salary vs program median"
            value={inputs.salary_adjust_pct}
            min={-40}
            max={40}
            step={5}
            format={(v) => `${v > 0 ? "+" : ""}${v}% · ${lakhs(roi.salary.start_lakhs)}/yr`}
            onChange={(v) => set("salary_adjust_pct", v)}
          />
          <details className="text-sm">
            <summary className="cursor-pointer text-gray-600 dark:text-gray-400">More assumptions</summary>
            <div className="mt-3 space-y-3">
              {abroad && (
                <Slider
                  label="Rupee weakens per year"
                  value={inputs.inr_depreciation_pct}
                  min={0}
                  max={10}
                  step={0.5}
                  format={(v) => `${v}%`}
                  onChange={(v) => set("inr_depreciation_pct", v)}
                />
              )}
              <Slider
                label="Share of salary saved for repayment"
                value={inputs.savings_rate_pct}
                min={15}
                max={60}
                step={5}
                format={(v) => `${v}%`}
                onChange={(v) => set("savings_rate_pct", v)}
              />
              <Slider
                label="Illustrative loan rate"
                value={inputs.loan_rate_pct}
                min={8}
                max={15}
                step={0.25}
                format={(v) => `${v}%`}
                onChange={(v) => set("loan_rate_pct", v)}
              />
            </div>
          </details>
        </div>

        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Net position after graduating (₹ lakhs)</p>
            <div className="mt-2 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#9ca3af33" />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" />
                  <Tooltip formatter={(v: number) => lakhs(v)} contentStyle={{ fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine y={0} stroke="#6b7280" />
                  <Line type="monotone" dataKey="chosen" name="This program" stroke="#4f46e5" strokeWidth={2.5} dot={false} />
                  {alt && <Line type="monotone" dataKey="alt" name={altLabel} stroke="#10b981" strokeWidth={2} strokeDasharray="5 4" dot={false} />}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[11px] text-gray-500">Savings minus total cost and all loan interest. It crosses zero at payback.</p>
          </div>

          <div className="overflow-hidden rounded-lg border border-gray-200 text-sm dark:border-gray-800">
            <table className="w-full">
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {[
                  ["Tuition", roi.cost.tuition_lakhs],
                  ["Living", roi.cost.living_lakhs],
                  ["Rupee buffer", roi.cost.fx_buffer_lakhs],
                  ["Visa, flights, insurance", roi.cost.one_time_lakhs],
                  ["Scholarship", -roi.cost.scholarship_lakhs],
                  ["Loan interest (est.)", roi.loan.total_interest_lakhs],
                ]
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <tr key={k as string}>
                      <td className="px-3 py-1.5 text-gray-600 dark:text-gray-400">{k}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{lakhs(v as number)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {alt && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{abroad ? "Abroad vs India" : "India vs abroad"}</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
                  <th className="py-1 font-medium" />
                  <th className="py-1 font-medium">This program</th>
                  <th className="py-1 font-medium">
                    <Link href={`/programs/${alt.program.course_id}`} className="text-indigo-600 hover:underline">
                      {alt.program.program}, {altLabel} →
                    </Link>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 tabular-nums dark:divide-gray-800">
                {[
                  ["Admit odds", pct(detail.admit.chance), pct(alt.chance)],
                  ["Total cost", lakhs(roi.cost.total_lakhs), lakhs(alt.roi.cost.total_lakhs)],
                  ["Loan needed", lakhs(roi.funding.gap_lakhs), lakhs(alt.roi.funding.gap_lakhs)],
                  ["Starting salary", `${lakhs(roi.salary.start_lakhs)}/yr (${roi.salary.location})`, `${lakhs(alt.roi.salary.start_lakhs)}/yr (${alt.roi.salary.location})`],
                  ["Payback", payback(roi.outcome.payback_years), payback(alt.roi.outcome.payback_years)],
                  ["10-year net gain", lakhs(roi.outcome.ten_year_net_lakhs), lakhs(alt.roi.outcome.ten_year_net_lakhs)],
                ].map(([k, a, b]) => (
                  <tr key={k}>
                    <td className="py-1.5 pr-3 text-gray-600 dark:text-gray-400">{k}</td>
                    <td className="py-1.5 pr-3 font-medium">{a}</td>
                    <td className="py-1.5">{b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {roi.funding.gap_lakhs > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-indigo-50 p-4 dark:bg-indigo-950">
          <div className="text-sm text-indigo-950 dark:text-indigo-100">
            <p className="font-semibold">You may need about {lakhs(roi.funding.gap_lakhs)} in education loan</p>
            <p className="text-xs opacity-80">
              EMI starts after a {roi.loan.moratorium_months}-month moratorium. Collateral and co-applicant income change what lenders offer.
            </p>
          </div>
          <Link
            href={`/mentor?q=${encodeURIComponent(`How can I fund the ${lakhs(roi.funding.gap_lakhs)} gap for ${detail.program.program} at ${detail.program.university}? Do I need collateral?`)}`}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Ask the mentor about funding
          </Link>
        </div>
      )}
      <p className="text-[11px] text-gray-500">{detail.roi_note}</p>
    </Card>
  );
}

export default function ProgramPage() {
  const { id } = useParams<{ id: string }>();
  const { me, loading } = useMe();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [starred, setStarred] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!me?.profile) return;
    setDetail(null);
    api<Detail>(`/programs/${id}`)
      .then((d) => {
        setDetail(d);
        setStarred(d.shortlisted);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [me, id]);

  async function toggleStar() {
    const r = await api<{ shortlist: number[] }>(`/navigator/shortlist/${id}`, { method: starred ? "DELETE" : "POST" });
    setStarred(r.shortlist.includes(Number(id)));
  }

  if (loading) return <main className="p-6 text-gray-500">Loading…</main>;
  if (me && !me.profile) {
    return (
      <main className="mx-auto max-w-xl space-y-4 p-6 text-center">
        <p className="text-gray-600 dark:text-gray-400">Take the 2-minute quiz first so we can estimate your odds.</p>
        <Link href="/onboarding" className="inline-block rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white">
          Start the quiz
        </Link>
      </main>
    );
  }
  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!detail) return <main className="p-6 text-gray-500">Crunching your odds and ROI…</main>;

  const p = detail.program;
  return (
    <main className="mx-auto max-w-5xl space-y-5 p-4 sm:p-8">
      <header className="space-y-2">
        <Link href="/navigator" className="text-sm text-gray-500 hover:underline">
          ← Navigator
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{p.university}</h1>
            <p className="text-gray-600 dark:text-gray-400">
              {p.program} · {p.city}, {p.country}
            </p>
          </div>
          <button
            onClick={toggleStar}
            className={`rounded-full px-3 py-1.5 text-sm ${starred ? "bg-amber-400 text-amber-950" : "border border-gray-300 dark:border-gray-700"}`}
          >
            {starred ? "★ Saved" : "☆ Save"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-gray-500">
          {p.qs_rank && <span>QS ~#{p.qs_rank}</span>}
          <span>{p.duration_months} months</span>
          {p.stem && <span>STEM</span>}
          <span>Deadline ~{MONTHS[p.deadline_month - 1]}</span>
        </div>
      </header>

      <AdmitPanel key={`a${id}`} courseId={id} detail={detail} />
      <RoiPanel key={`r${id}`} courseId={id} detail={detail} />

      <p className="text-xs text-gray-500">
        {detail.model.kind === "ml"
          ? `Admit odds come from a ${detail.model.algorithm} trained on ${detail.model.trained_rows?.toLocaleString("en-IN")} synthetic applications (AUC ${detail.model.auc} on programs it never saw). `
          : "Admit odds use a calibrated heuristic. "}
        They are estimates, not guarantees. {detail.disclaimer}
      </p>
    </main>
  );
}
