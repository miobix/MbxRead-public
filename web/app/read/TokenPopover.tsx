"use client";

import { useState } from "react";
import { api, type DictEntry, type Term, type TermStatus, type TermSummary } from "@/lib/api";

export type PopoverTarget = {
  surface: string;
  lemma: string;
  sentence: string;
  existing: TermSummary | null;
};

export function TokenPopover({
  target,
  decks,
  defaultDeck,
  translatorBackend,
  onClose,
  onSaved,
  onDeleted,
}: {
  target: PopoverTarget;
  decks: string[];
  defaultDeck: string;
  translatorBackend?: string;
  onClose: () => void;
  onSaved: (originalLemma: string, newLemma: string, term: Term) => void;
  onDeleted: (lemma: string) => void;
}) {
  const isEditing = target.existing !== null;
  const deckOptions =
    target.existing?.deck && !decks.includes(target.existing.deck)
      ? [...decks, target.existing.deck]
      : decks;

  const [lemma, setLemma] = useState(target.lemma);
  const [translation, setTranslation] = useState(target.existing?.translation ?? "");
  const [deck, setDeck] = useState(target.existing?.deck || defaultDeck);
  const [dictEntries, setDictEntries] = useState<DictEntry[] | null>(null);
  const [busy, setBusy] = useState<"translate" | "dict" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const translateWord = async () => {
    if (!lemma.trim()) return;
    setBusy("translate");
    setError(null);
    try {
      const { translation: result } = await api.translate(lemma.trim(), translatorBackend);
      setTranslation(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Translation failed.");
    } finally {
      setBusy(null);
    }
  };

  const lookupDictionary = async () => {
    if (!lemma.trim()) return;
    setBusy("dict");
    setError(null);
    try {
      setDictEntries(await api.dictLookup(lemma.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dictionary lookup failed.");
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    const trimmedLemma = lemma.trim();
    if (!trimmedLemma) {
      setError("Lemma can't be empty.");
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const term = target.existing
        ? await api.patchTerm(target.existing.id, {
            lemma: trimmedLemma,
            translation: translation.trim(),
            deck,
            sentence: target.sentence,
          })
        : await api.createTerm({
            lemma: trimmedLemma,
            translation: translation.trim(),
            deck,
            sentence: target.sentence,
            status: "learning",
          });
      onSaved(target.lemma, trimmedLemma, term);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save.");
      setBusy(null);
    }
  };

  const setStatus = async (status: TermStatus) => {
    if (!target.existing) return;
    setBusy("save");
    setError(null);
    try {
      const term = await api.patchTerm(target.existing.id, { status });
      onSaved(target.lemma, target.lemma, term);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update.");
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!target.existing) return;
    setBusy("save");
    setError(null);
    try {
      await api.deleteTerm(target.existing.id);
      onDeleted(target.lemma);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete.");
      setBusy(null);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-md bg-surface shadow-xl rounded-t-2xl sm:rounded-2xl p-5 flex flex-col gap-3 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-sm text-muted">{target.surface}</div>

        <input
          value={lemma}
          onChange={(e) => setLemma(e.target.value)}
          placeholder="Dictionary form (lemma)"
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        />

        <div className="flex gap-2 flex-wrap">
          <button
            onClick={translateWord}
            disabled={busy !== null}
            className="px-3 py-1.5 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
          >
            {busy === "translate" ? "Translating…" : "Translate"}
          </button>
          <button
            onClick={lookupDictionary}
            disabled={busy !== null}
            className="px-3 py-1.5 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
          >
            {busy === "dict" ? "Looking up…" : "Dictionary"}
          </button>
        </div>

        {target.sentence && <p className="text-xs text-muted italic">{target.sentence}</p>}

        {dictEntries && (
          <div className="flex flex-col gap-2 max-h-40 overflow-y-auto border-t border-border pt-2">
            {dictEntries.length === 0 && (
              <p className="text-xs text-muted">No dictionary entries found.</p>
            )}
            {dictEntries.map((entry, i) => (
              <div key={i} className="text-xs">
                <span className="font-medium">{entry.word}</span>{" "}
                <span className="text-muted">{entry.pos}</span>
                <ul className="list-disc list-inside text-muted">
                  {entry.definitions.map((d, j) => (
                    <li key={j}>
                      <b>{d.en_word}</b> — {d.en_def}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        <textarea
          value={translation}
          onChange={(e) => setTranslation(e.target.value)}
          placeholder="Translation / notes…"
          rows={4}
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        />

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

        {error && <p className="text-danger text-sm">{error}</p>}

        {isEditing && (
          <div className="flex gap-2 flex-wrap text-sm">
            <button
              onClick={() => setStatus("known")}
              disabled={busy !== null}
              className="px-3 py-1.5 rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
            >
              Mark known
            </button>
            <button
              onClick={() => setStatus("ignored")}
              disabled={busy !== null}
              className="px-3 py-1.5 rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
            >
              Ignore
            </button>
            <button
              onClick={remove}
              disabled={busy !== null}
              className="px-3 py-1.5 rounded-full border border-danger-soft text-danger hover:bg-danger/10 transition-colors disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        )}

        <div className="flex gap-2 justify-end mt-1">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-full border border-border hover:bg-paper transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy !== null}
            className="px-4 py-2 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {busy === "save" ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
