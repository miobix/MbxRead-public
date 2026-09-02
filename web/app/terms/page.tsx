"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AnkiSyncResult, type Settings, type Term, type TermStatus } from "@/lib/api";
import { TokenPopover } from "../read/TokenPopover";

const STATUSES: TermStatus[] = ["learning", "known", "ignored"];

export default function TermsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [terms, setTerms] = useState<Term[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState<TermStatus | "">("");
  const [deck, setDeck] = useState("");
  const [q, setQ] = useState("");

  // Epic 22 follow-up: editing reuses the reader's full card-builder popover
  // (dictionary/translate/forms/back_items/examples) instead of the old flat
  // lemma/translation/notes textareas — that gap predated this epic (Epic 20/21
  // never touched /terms either) and the user asked for parity.
  const [editingTerm, setEditingTerm] = useState<Term | null>(null);
  // Epic 25: on-demand hanja saves reuse the same popover, opened target-less
  // (no existing term, no book/page) with hanjaMode on.
  const [addingWord, setAddingWord] = useState(false);

  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<AnkiSyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {
      // best-effort — deck select just falls back to whatever GET /api/terms returns
    });
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      api
        .listTerms({ status: status || undefined, deck: deck || undefined, q: q || undefined })
        .then(setTerms)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load terms."));
    }, 250);
    return () => clearTimeout(handle);
  }, [status, deck, q]);

  const refresh = () => {
    api
      .listTerms({ status: status || undefined, deck: deck || undefined, q: q || undefined })
      .then(setTerms)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load terms."));
  };

  const sync = async () => {
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      setSyncResult(await api.syncAnki());
      refresh();
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  const handleSaved = (term: Term) => {
    setTerms((prev) => prev?.map((t) => (t.id === term.id ? term : t)) ?? prev);
  };

  const handleDeleted = (id: number) => {
    setTerms((prev) => prev?.filter((t) => t.id !== id) ?? prev);
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold font-serif">Terms</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setAddingWord(true)}
            className="rounded-full border border-border px-4 py-2 text-sm font-medium hover:border-accent transition-colors"
          >
            Add word
          </button>
          <button
            onClick={sync}
            disabled={syncing}
            className="rounded-full bg-accent text-accent-ink px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync to Anki"}
          </button>
        </div>
      </div>

      {syncError && <p className="text-danger text-sm">{syncError}</p>}

      {syncResult && (
        <div className="rounded-xl border border-border bg-surface shadow-sm p-4 text-sm flex flex-col gap-2">
          <p>
            Added <b>{syncResult.added}</b>, updated <b>{syncResult.updated}</b>
            {syncResult.failed.length > 0 && (
              <>
                , failed <b>{syncResult.failed.length}</b>
              </>
            )}
            .
          </p>
          {syncResult.failed.length > 0 && (
            <ul className="list-disc list-inside text-danger">
              {syncResult.failed.map((f, i) => (
                <li key={i}>
                  {f.lemma}: {f.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as TermStatus | "")}
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={deck}
          onChange={(e) => setDeck(e.target.value)}
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        >
          <option value="">All decks</option>
          {(settings?.decks ?? []).map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>

        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search lemma / translation…"
          className="flex-1 min-w-[10rem] rounded-lg border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        />
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}

      {terms === null && !error && <p className="text-muted">Loading…</p>}

      {terms?.length === 0 && <p className="text-muted">No terms match.</p>}

      <ul className="flex flex-col gap-2">
        {terms?.map((term) => (
          <li
            key={term.id}
            onClick={() => setEditingTerm(term)}
            className="rounded-xl border border-border bg-surface shadow-sm p-3 text-sm cursor-pointer hover:border-accent transition-colors"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">
                {term.lemma}
                {term.hanja && <span className="text-muted font-normal"> {term.hanja}</span>}
              </span>
              <span className="text-xs text-muted">
                {term.status}
                {term.deck && ` · ${term.deck}`}
              </span>
            </div>
            {term.translation && (
              <div className="text-muted mt-1">{term.translation}</div>
            )}
          </li>
        ))}
      </ul>

      {editingTerm && (
        <TokenPopover
          target={{
            surface: editingTerm.lemma,
            lemma: editingTerm.lemma,
            sentence: editingTerm.sentence,
            // Same phrase heuristic the reader uses (whitespace in the lemma) —
            // multi-word terms get the translate-only UI, no dictionary/forms.
            isPhrase: /\s/.test(editingTerm.lemma),
            existing: {
              id: editingTerm.id,
              lemma: editingTerm.lemma,
              translation: editingTerm.translation,
              notes: editingTerm.notes,
              status: editingTerm.status,
              deck: editingTerm.deck,
              forms: editingTerm.forms,
              examples: editingTerm.examples,
              back_items: editingTerm.back_items,
              hanja: editingTerm.hanja,
            },
          }}
          bookId={null}
          pageNo={null}
          decks={settings?.decks ?? []}
          defaultDeck={settings?.default_deck ?? ""}
          translatorBackend={settings?.translator_backend}
          onClose={() => setEditingTerm(null)}
          onSaved={handleSaved}
          onDeleted={(t) => handleDeleted(t.id)}
        />
      )}

      {addingWord && (
        <TokenPopover
          target={{
            surface: "",
            lemma: "",
            sentence: "",
            isPhrase: false,
            existing: null,
          }}
          bookId={null}
          pageNo={null}
          decks={settings?.decks ?? []}
          defaultDeck={settings?.hanja_deck || settings?.default_deck || ""}
          translatorBackend={settings?.translator_backend}
          hanjaMode
          onClose={() => setAddingWord(false)}
          onSaved={() => refresh()}
          onDeleted={() => {}}
        />
      )}
    </main>
  );
}
