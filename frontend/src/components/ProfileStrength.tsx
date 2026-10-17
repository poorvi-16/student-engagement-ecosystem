import type { Strength } from "@/lib/api";

function band(score: number) {
  if (score >= 75) return { label: "Strong", color: "text-emerald-600", ring: "stroke-emerald-500" };
  if (score >= 50) return { label: "Good", color: "text-indigo-600", ring: "stroke-indigo-500" };
  if (score >= 30) return { label: "Building", color: "text-amber-600", ring: "stroke-amber-500" };
  return { label: "Getting started", color: "text-rose-600", ring: "stroke-rose-500" };
}

export function ProfileStrength({ strength }: { strength: Strength }) {
  const b = band(strength.score);
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
      <div className="relative mx-auto h-36 w-36">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
          <circle cx="60" cy="60" r={r} className="fill-none stroke-gray-200 dark:stroke-gray-800" strokeWidth="10" />
          <circle
            cx="60"
            cy="60"
            r={r}
            className={`fill-none ${b.ring} transition-all duration-700`}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - strength.score / 100)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold">{strength.score}</span>
          <span className={`text-xs font-medium ${b.color}`}>{b.label}</span>
        </div>
      </div>
      <div className="space-y-2">
        {strength.dimensions.map((d) => (
          <div key={d.key}>
            <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
              <span>{d.label}</span>
              <span>
                {Math.round(d.score)}/{d.max}
              </span>
            </div>
            <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-800">
              <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${(d.score / d.max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      {strength.tips.length > 0 && (
        <ul className="space-y-1.5 text-sm sm:col-span-2">
          {strength.tips.map((t) => (
            <li key={t} className="flex gap-2">
              <span aria-hidden>💡</span>
              <span>{t}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
