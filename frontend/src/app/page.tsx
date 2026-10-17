import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-5 p-6 text-center">
      <h1 className="text-4xl font-bold sm:text-5xl">PathPilot</h1>
      <p className="max-w-md text-gray-600 dark:text-gray-400">
        Your AI copilot for higher studies — find the right university, plan your applications, and fund your future.
      </p>
      <Link href="/login" className="rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700">
        Get started — it&apos;s free
      </Link>
    </main>
  );
}
