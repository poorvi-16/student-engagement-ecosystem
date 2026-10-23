import Link from "next/link";

/** Shown on every page: the prototype and simulated-finance disclosure, plus the privacy link. */
export function SiteFooter() {
  return (
    <footer className="mt-10 border-t border-gray-200 px-4 py-6 text-center text-xs text-gray-500 dark:border-gray-800">
      <p>
        PathPilot is a prototype. Loan offers, credit checks and lender decisions are <strong>simulated</strong> and are not financial advice.
      </p>
      <p className="mt-1 space-x-3">
        <Link href="/privacy" className="underline">
          Privacy and your data
        </Link>
        <Link href="/guides" className="underline">
          Guides
        </Link>
      </p>
    </footer>
  );
}
