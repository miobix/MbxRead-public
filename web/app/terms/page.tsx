"use client";

import { BackLink } from "@/lib/back-link";
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

  // Editing reuses the reader's card-builder popover.
  const [editingTerm, setEditingTerm] = useState<Term | null>(null);
  // "Add word" opens the same popover with no term or book, in hanjaMode.
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
      <BackLink />

      <div className="flex items-center justify-between gap-2">
        <h1 className="page-title">Terms</h1>
        <div className="flex gap-2 flex-wrap justify-end">
          <button
            onClick={() => setAddingWord(true)}
            className="btn-secondary"
          >
            Add word
          </button>
          <Link href="/terms/batch" className="btn-secondary">
            Add batch
          </Link>
          <button
            onClick={sync}
            disabled={syncing}
            className="btn-primary"
          >
            {syncing ? "Syncing…" : "Sync to Anki"}
          </button>
        </div>
      </div>

      {syncError && <p className="text-danger text-sm">{syncError}</p>}

      {syncResult && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm flex flex-col gap-2">
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
          className="field"
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
          className="field"
        >
          <option value="">All decks</option>
          {/* hanja_deck is a separate setting, so merge it in or hanja saves can't be
              filtered. */}
          {[...new Set([...(settings?.decks ?? []), settings?.hanja_deck].filter(
            (d): d is string => !!d
          ))].map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>

        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search lemma / translation…"
          className="flex-1 min-w-[10rem] field"
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
            className="rounded-lg border border-border bg-surface p-3 text-sm cursor-pointer hover:border-accent transition-colors"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">
                {term.lemma}
                {term.hanja.length > 0 && (
                  <span className="text-muted font-normal"> {term.hanja.join(" · ")}</span>
                )}
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
          hanjaDeck={settings?.hanja_deck}
          onClose={() => setAddingWord(false)}
          onSaved={() => refresh()}
          onDeleted={() => {}}
        />
      )}
    </main>
  );
}
