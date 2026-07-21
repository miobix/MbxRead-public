"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type AnkiSyncResult } from "@/lib/api";

// Bare-bones stub for Epic 6 (Anki sync) — the full table/filter/inline-edit
// page is Epic 7 scope. See docs/DECISIONS.md.
export default function TermsPage() {
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState<AnkiSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sync = async () => {
    setSyncing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.syncAnki());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-zinc-500 self-start">
        ← Books
      </Link>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Terms</h1>
        <button
          onClick={sync}
          disabled={syncing}
          className="rounded-full bg-zinc-900 text-white px-4 py-2 text-sm font-medium dark:bg-white dark:text-zinc-900 disabled:opacity-50"
        >
          {syncing ? "Syncing…" : "Sync to Anki"}
        </button>
      </div>

      {error && <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>}

      {result && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 text-sm flex flex-col gap-2">
          <p>
            Added <b>{result.added}</b>, updated <b>{result.updated}</b>
            {result.failed.length > 0 && (
              <>
                , failed <b>{result.failed.length}</b>
              </>
            )}
            .
          </p>
          {result.failed.length > 0 && (
            <ul className="list-disc list-inside text-red-600 dark:text-red-400">
              {result.failed.map((f, i) => (
                <li key={i}>
                  {f.lemma}: {f.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="text-sm text-zinc-500">
        The full terms table (filter, inline edit, delete) is coming in a later
        update — for now this page just triggers the Anki sync.
      </p>
    </main>
  );
}
