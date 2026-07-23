"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AnkiSyncResult, type Settings, type Term, type TermStatus } from "@/lib/api";

const STATUSES: TermStatus[] = ["learning", "known", "ignored"];

export default function TermsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [terms, setTerms] = useState<Term[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState<TermStatus | "">("");
  const [deck, setDeck] = useState("");
  const [q, setQ] = useState("");

  const [editingId, setEditingId] = useState<number | null>(null);

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
    setEditingId(null);
  };

  const handleDeleted = (id: number) => {
    setTerms((prev) => prev?.filter((t) => t.id !== id) ?? prev);
    setEditingId(null);
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-serif">Terms</h1>
        <button
          onClick={sync}
          disabled={syncing}
          className="rounded-full bg-accent text-accent-ink px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {syncing ? "Syncing…" : "Sync to Anki"}
        </button>
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
        {terms?.map((term) =>
          editingId === term.id ? (
            <TermEditRow
              key={term.id}
              term={term}
              decks={settings?.decks ?? []}
              onCancel={() => setEditingId(null)}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
            />
          ) : (
            <li
              key={term.id}
              onClick={() => setEditingId(term.id)}
              className="rounded-xl border border-border bg-surface shadow-sm p-3 text-sm cursor-pointer hover:border-accent transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{term.lemma}</span>
                <span className="text-xs text-muted">
                  {term.status}
                  {term.deck && ` · ${term.deck}`}
                </span>
              </div>
              {term.translation && (
                <div className="text-muted mt-1">{term.translation}</div>
              )}
            </li>
          )
        )}
      </ul>
    </main>
  );
}

function TermEditRow({
  term,
  decks,
  onCancel,
  onSaved,
  onDeleted,
}: {
  term: Term;
  decks: string[];
  onCancel: () => void;
  onSaved: (term: Term) => void;
  onDeleted: (id: number) => void;
}) {
  const [lemma, setLemma] = useState(term.lemma);
  const [translation, setTranslation] = useState(term.translation);
  const [notes, setNotes] = useState(term.notes);
  const [deck, setDeck] = useState(term.deck);
  const [status, setStatus] = useState<TermStatus>(term.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deckOptions = term.deck && !decks.includes(term.deck) ? [...decks, term.deck] : decks;

  const save = async () => {
    const trimmedLemma = lemma.trim();
    if (!trimmedLemma) {
      setError("Lemma can't be empty.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patchTerm(term.id, {
        lemma: trimmedLemma,
        translation: translation.trim(),
        notes: notes.trim(),
        deck,
        status,
      });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save.");
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteTerm(term.id);
      onDeleted(term.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete.");
      setBusy(false);
    }
  };

  return (
    <li
      className="rounded-xl border border-accent bg-surface shadow-sm p-3 text-sm flex flex-col gap-2"
      onClick={(e) => e.stopPropagation()}
    >
      <input
        value={lemma}
        onChange={(e) => setLemma(e.target.value)}
        placeholder="Dictionary form (lemma)"
        className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
      />

      <textarea
        value={translation}
        onChange={(e) => setTranslation(e.target.value)}
        placeholder="Translation"
        rows={3}
        className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
      />

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes"
        rows={2}
        className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
      />

      <div className="flex gap-2 flex-wrap">
        <select
          value={deck}
          onChange={(e) => setDeck(e.target.value)}
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        >
          {deckOptions.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>

        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as TermStatus)}
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}

      <div className="flex gap-2 justify-between mt-1">
        <button
          onClick={remove}
          disabled={busy}
          className="px-3 py-1.5 text-sm rounded-full border border-danger-soft text-danger hover:bg-danger/10 transition-colors disabled:opacity-50"
        >
          Delete
        </button>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm rounded-full border border-border hover:bg-paper transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="px-4 py-2 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </li>
  );
}
