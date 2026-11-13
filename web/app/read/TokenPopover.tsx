"use client";

import { useState } from "react";
import {
  api,
  type BackItem,
  type DictEntry,
  type FormEntry,
  type Term,
  type TermStatus,
  type TermSummary,
} from "@/lib/api";

export type PopoverTarget = {
  surface: string;
  lemma: string;
  sentence: string;
  existing: TermSummary | null;
  // Multi-word phrase selection → translate-only UI (no dictionary/forms/examples).
  isPhrase: boolean;
};

// Dictionary-derived chips run strong→pale across this "blue family" in
// the order they're added this session (front forms + back senses, combined).
const DICT_SHADES = ["bg-dict-1", "bg-dict-2", "bg-dict-3", "bg-dict-4"];
const dictShade = (i: number) => DICT_SHADES[Math.min(i, DICT_SHADES.length - 1)];

const LEMMA_GROUP = "";

// Rough rendered width in em, so the lemma input hugs its text: Hangul/Hanja are
// about 1em wide, everything else about 0.6em.
const textEm = (text: string) =>
  [...text].reduce((w, ch) => w + (/[\u1100-\u11ff\u3000-\u9fff\uac00-\ud7af]/.test(ch) ? 1 : 0.6), 0);

export function TokenPopover({
  target,
  bookId,
  pageNo,
  decks,
  defaultDeck,
  translatorBackend,
  onClose,
  onSaved,
  onDeleted,
}: {
  target: PopoverTarget;
  bookId: number | null;
  pageNo: number | null;
  decks: string[];
  defaultDeck: string;
  translatorBackend?: string;
  onClose: () => void;
  onSaved: (term: Term) => void;
  onDeleted: (term: TermSummary) => void;
}) {
  const isEditing = target.existing !== null;
  // Phrases are translate-only: a multi-word span has no single dictionary lemma.
  const isPhrase = target.isPhrase;
  // Include the deck the save will use (the term's, or defaultDeck), which may not be
  // in the user's `decks` list.
  const deckOptions = [...new Set([...decks, target.existing?.deck, defaultDeck])].filter(
    (d): d is string => !!d
  );

  // When a saved word is tapped via one of its extra forms (e.g. 승인서), the token
  // lemma is that form — show the term's real dictionary form (승인) instead.
  const [lemma, setLemma] = useState(target.existing?.lemma ?? target.lemma);
  const [deck, setDeck] = useState(target.existing?.deck || defaultDeck);
  const [forms, setForms] = useState<FormEntry[]>(target.existing?.forms ?? []);
  const [backItems, setBackItems] = useState<BackItem[]>(target.existing?.back_items ?? []);
  const [notes, setNotes] = useState(target.existing?.notes ?? "");
  // An existing term found by lemma while adding a new word — the save turns into
  // an append onto it rather than a create that the UNIQUE lemma would refuse.
  const [appendTo, setAppendTo] = useState<Term | null>(null);
  const [dictEntries, setDictEntries] = useState<DictEntry[] | null>(null);
  const [manualFront, setManualFront] = useState("");
  const [manualBack, setManualBack] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"translate" | "dict" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A term never touched by this card builder (no back_items) shows its old flat
  // translation read-only instead of chips.
  const legacyTranslation =
    (target.existing?.back_items.length ?? 0) === 0 ? target.existing?.translation || "" : "";

  const groupKeyFor = (text: string) => (text === lemma.trim() ? LEMMA_GROUP : text);

  // The term this save will write to: the tapped/edited one, or one found by lemma.
  const targetTerm: TermSummary | Term | null = target.existing ?? appendTo;

  // Fold an already-saved term into this popover so the save becomes an append.
  // Merges rather than replaces: anything already typed here survives.
  const adoptExisting = (term: Term) => {
    setAppendTo(term);
    setForms((prev) => [
      ...term.forms,
      ...prev.filter((f) => !term.forms.some((e) => e.text === f.text)),
    ]);
    setBackItems((prev) => [
      ...term.back_items,
      ...prev.filter(
        (b) =>
          !term.back_items.some(
            (e) => e.group === b.group && e.kind === b.kind && e.text === b.text
          )
      ),
    ]);
    setNotes((prev) => prev || term.notes);
    if (term.deck) setDeck(term.deck);
  };

  const removeForm = (index: number) => {
    const removed = forms[index];
    setForms((prev) => prev.filter((_, i) => i !== index));
    setBackItems((prev) => prev.filter((b) => b.group !== removed.text));
  };

  const removeBackItem = (index: number) =>
    setBackItems((prev) => prev.filter((_, i) => i !== index));

  const addDictSense = (
    group: string,
    def: { ko: string; en_word: string; en_def: string },
    example: string | undefined
  ) => {
    const text = def.en_word || def.en_def;
    if (!text) return;
    const koreanDef = def.ko + (example ?? "");
    setBackItems((prev) => {
      if (prev.some((b) => b.group === group && b.kind === "dict" && b.text === text)) {
        return prev;
      }
      return [...prev, { group, kind: "dict", text, korean_def: koreanDef }];
    });
  };

  const addDictHeadword = (entry: DictEntry) => {
    const text = entry.word.trim();
    if (!text) return;
    const group = groupKeyFor(text);
    if (group !== LEMMA_GROUP && !forms.some((f) => f.text === group)) {
      setForms((prev) => [...prev, { text: group, kind: "dict" }]);
    }
    if (entry.definitions[0]) addDictSense(group, entry.definitions[0], entry.examples[0]);
  };

  const addManualEntry = () => {
    const front = manualFront.trim();
    if (!front) return;
    if (front === lemma.trim() || forms.some((f) => f.text === front)) {
      setManualError(`"${front}" is already used.`);
      return;
    }
    setForms((prev) => [...prev, { text: front, kind: "manual" }]);
    const back = manualBack.trim();
    if (back) {
      setBackItems((prev) => [
        ...prev,
        { group: front, kind: "manual", text: back, korean_def: "" },
      ]);
    }
    setManualFront("");
    setManualBack("");
    setManualError(null);
  };

  const addBackText = (text: string, group: string) => {
    const value = text.trim();
    if (!value) return;
    setBackItems((prev) => {
      if (prev.some((b) => b.group === group && b.kind === "manual" && b.text === value)) {
        return prev;
      }
      return [...prev, { group, kind: "manual", text: value, korean_def: "" }];
    });
  };

  const translateWord = async () => {
    if (!lemma.trim()) return;
    setBusy("translate");
    setError(null);
    try {
      const { translation: result } = await api.translate(lemma.trim(), translatorBackend);
      setBackItems((prev) => {
        if (prev.some((b) => b.group === LEMMA_GROUP && b.kind === "translate" && b.text === result)) {
          return prev;
        }
        return [...prev, { group: LEMMA_GROUP, kind: "translate", text: result, korean_def: "" }];
      });
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
    // An empty back_items array would blank a chip-less term's translation on save.
    const backItemsPayload = backItems.length > 0 ? backItems : undefined;
    try {
      const term = targetTerm
        ? await api.patchTerm(targetTerm.id, {
            lemma: trimmedLemma,
            deck,
            // Appending from /terms carries no sentence; don't let that blank out
            // the one an existing reading-flow term already captured.
            sentence: target.sentence || undefined,
            notes,
            forms,
            back_items: backItemsPayload,
          })
        : await api.createTerm({
            lemma: trimmedLemma,
            translation: "",
            deck,
            sentence: target.sentence,
            notes,
            forms,
            back_items: backItemsPayload,
            status: "learning",
            // Where the word was first saved, for per-book stats.
            source_book_id: bookId ?? undefined,
            source_page: pageNo ?? undefined,
          });
      onSaved(term);
      onClose();
    } catch (e) {
      // A 409 means the word is already saved: turn it into the append offer.
      const clash = targetTerm ? null : await api.termByLemma(trimmedLemma);
      if (clash) {
        adoptExisting(clash);
        setError(`${trimmedLemma} is already saved. Press "Add to ${trimmedLemma}" to add to it.`);
      } else {
        setError(e instanceof Error ? e.message : "Failed to save.");
      }
      setBusy(null);
    }
  };

  const setStatus = async (status: TermStatus) => {
    if (!target.existing) return;
    setBusy("save");
    setError(null);
    try {
      const term = await api.patchTerm(target.existing.id, { status });
      onSaved(term);
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
      onDeleted(target.existing);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete.");
      setBusy(null);
    }
  };

  // Front stack: the lemma's own group first, then each extra form — mirrors the
  // Anki renderer's _front_entries exactly, so the preview is a true WYSIWYG.
  const frontEntries = [{ text: lemma.trim() || lemma, kind: "lemma" as const }, ...forms];

  // Running shade index for dictionary-derived chips, front forms then back items.
  let dictCounter = 0;
  const formShade = forms.map((f) => (f.kind === "dict" ? dictShade(dictCounter++) : ""));
  const backShade = backItems.map((b) => (b.kind === "dict" ? dictShade(dictCounter++) : ""));

  const chipClass = (kind: "lemma" | "dict" | "translate" | "manual", shade: string) => {
    if (kind === "lemma" || kind === "manual") return "bg-manual text-manual-ink";
    if (kind === "translate") return "bg-translate text-translate-ink";
    return `${shade || "bg-dict-1"} text-dict-ink`;
  };

  // Pre-Epic-32 hanja chips are grouped by a spelling no front entry has; show them
  // under the lemma, as the Anki sync does.
  const frontGroups = new Set([LEMMA_GROUP, ...forms.map((f) => f.text)]);
  const backItemsFor = (group: string) =>
    backItems.filter((b) => (frontGroups.has(b.group) ? b.group : LEMMA_GROUP) === group);
  const backIndexOf = (item: BackItem) => backItems.indexOf(item);

  // The "→ meaning meaning" run of one front entry's preview row.
  const backRow = (group: string) => {
    const items = backItemsFor(group);
    return (
      <>
        {items.length > 0 && <span className="text-muted">→</span>}
        {items.map((item) => {
          const bi = backIndexOf(item);
          return (
            <span
              key={bi}
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 ${chipClass(
                item.kind,
                backShade[bi]
              )}`}
            >
              {item.text}
              <button
                type="button"
                onClick={() => removeBackItem(bi)}
                aria-label={`Remove ${item.text}`}
                className="opacity-80 hover:opacity-100"
              >
                ×
              </button>
            </span>
          );
        })}
      </>
    );
  };

  return (
    <div
      className="fixed inset-0 bg-black/25 flex items-end sm:items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-md bg-surface border-t border-border sm:border sm:rounded-lg shadow-[0_-8px_30px_rgb(0_0_0/0.12)] px-6 pt-5 pb-6 flex flex-col gap-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-col gap-1">
          {target.surface !== lemma && (
            <span className="text-sm text-muted">{target.surface}</span>
          )}
          <div className="flex items-baseline gap-3">
            <input
              value={lemma}
              onChange={(e) => setLemma(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isPhrase && busy === null) {
                  e.preventDefault();
                  lookupDictionary();
                }
              }}
              autoFocus={!isEditing && !target.lemma}
              placeholder="Dictionary form"
              aria-label="Dictionary form (lemma)"
              style={{ width: `${Math.max(3, textEm(lemma)) + 0.5}em` }}
              className={`min-w-0 max-w-full bg-transparent font-bold leading-tight border-b border-transparent hover:border-border focus:border-accent focus:outline-none focus-visible:outline-none transition-colors ${
                isPhrase ? "text-xl" : "text-[32px]"
              }`}
            />
          </div>
        </div>

        {appendTo && (
          <p className="rounded border border-border bg-paper px-3 py-2 text-sm">
            <b>{appendTo.lemma}</b> is already saved
            {appendTo.translation && <> ({appendTo.translation})</>}. Saving adds to it.
          </p>
        )}

        {target.sentence && (
          <p className="text-sm leading-relaxed text-muted">{target.sentence}</p>
        )}

        <div className="flex flex-wrap gap-x-5 gap-y-2">
          <button onClick={translateWord} disabled={busy !== null} className="btn-link">
            {busy === "translate" ? "Translating…" : "Translate"}
          </button>
          {!isPhrase && (
            <button onClick={lookupDictionary} disabled={busy !== null} className="btn-link">
              {busy === "dict" ? "Looking up…" : "Dictionary"}
            </button>
          )}
        </div>

        {/* Front → Back preview, a WYSIWYG of what syncs to Anki: one row per front
            entry, so each Back chip sits next to the word it belongs to. */}
        <div className="flex flex-col divide-y divide-border border-y border-border text-sm">
          {legacyTranslation && (
            <div className="py-2 text-muted">Old translation: {legacyTranslation}</div>
          )}
          {frontEntries.map((entry, i) => {
            const group = i === 0 ? LEMMA_GROUP : entry.text;
            return (
              <div key={i} className="py-2 flex flex-wrap items-center gap-1.5">
                <span
                  className={`inline-flex items-center gap-1 rounded px-2 py-0.5 shrink-0 ${chipClass(
                    entry.kind === "lemma" ? "lemma" : entry.kind,
                    i === 0 ? "" : formShade[i - 1]
                  )}`}
                >
                  {entry.text}
                  {i > 0 && (
                    <button
                      type="button"
                      onClick={() => removeForm(i - 1)}
                      aria-label={`Remove ${entry.text}`}
                      className="opacity-80 hover:opacity-100"
                    >
                      ×
                    </button>
                  )}
                </span>
                {backRow(group)}
              </div>
            );
          })}
        </div>

        {!isPhrase && dictEntries && (
          <div className="flex flex-col gap-3 max-h-56 overflow-y-auto rounded border border-border bg-paper p-3">
            {dictEntries.length === 0 && (
              <p className="text-sm text-muted">No dictionary entries found.</p>
            )}
            {dictEntries.map((entry, i) => (
              <div key={i} className="text-sm">
                <button
                  type="button"
                  onClick={() => addDictHeadword(entry)}
                  className="font-semibold text-accent hover:underline"
                  title="Add as a highlighted form + first definition"
                >
                  {entry.word}
                </button>{" "}
                {entry.origin && <span className="text-muted">{entry.origin}</span>}{" "}
                <span className="text-xs text-muted">{entry.pos}</span>
                <ul className="mt-1 flex flex-col gap-1">
                  {entry.definitions.map((d, j) => (
                    <li key={j}>
                      <button
                        type="button"
                        onClick={() => addDictSense(groupKeyFor(entry.word.trim()), d, entry.examples[0])}
                        className="text-left text-muted hover:text-ink transition-colors"
                        title="Add this definition to Back"
                      >
                        <b className="text-ink font-medium">{d.en_word}</b>
                        {d.en_def ? `: ${d.en_def}` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* Examples: the literal content of the Anki "Examples" field. */}
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Examples</span>
          {backItems
            .map((item, i) => ({ item, i }))
            .filter(({ item }) => item.kind === "dict" && item.korean_def)
            .map(({ item, i }) => (
              <div key={i} className="flex items-start gap-1.5 text-sm">
                <button
                  type="button"
                  onClick={() => removeBackItem(i)}
                  aria-label="Remove definition"
                  className="text-muted hover:text-danger transition-colors"
                >
                  ×
                </button>
                <span>{item.korean_def}</span>
              </div>
            ))}
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes"
            rows={2}
            className="field resize-none"
          />
        </div>

        {/* Hand-typed content that never came from Translate/Dictionary. Always its
            own front group, never merged into the lemma. */}
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Add your own</span>
          {isPhrase ? (
            <div className="flex gap-2">
              <input
                value={manualBack}
                onChange={(e) => setManualBack(e.target.value)}
                placeholder="A translation"
                className="field flex-1 min-w-0"
              />
              <button
                type="button"
                onClick={() => {
                  addBackText(manualBack, LEMMA_GROUP);
                  setManualBack("");
                }}
                className="btn-secondary"
              >
                Add
              </button>
            </div>
          ) : (
            <>
              <div className="flex gap-2">
                <input
                  value={manualFront}
                  onChange={(e) => {
                    setManualFront(e.target.value);
                    setManualError(null);
                  }}
                  placeholder="Front"
                  className="field flex-1 min-w-0"
                />
                <input
                  value={manualBack}
                  onChange={(e) => setManualBack(e.target.value)}
                  placeholder="Back"
                  className="field flex-1 min-w-0"
                />
                <button type="button" onClick={addManualEntry} className="btn-secondary">
                  Add
                </button>
              </div>
              {manualError && <p className="text-danger text-sm">{manualError}</p>}
            </>
          )}
        </div>

        {error && <p className="text-danger text-sm">{error}</p>}

        {isEditing && (
          <div className="flex gap-x-5 gap-y-2 flex-wrap">
            {target.existing?.status !== "learning" && (
              <button onClick={() => setStatus("learning")} disabled={busy !== null} className="btn-quiet">
                Mark learning
              </button>
            )}
            {target.existing?.status !== "known" && (
              <button onClick={() => setStatus("known")} disabled={busy !== null} className="btn-quiet">
                Mark known
              </button>
            )}
            {target.existing?.status !== "ignored" && (
              <button onClick={() => setStatus("ignored")} disabled={busy !== null} className="btn-quiet">
                Ignore
              </button>
            )}
            <button
              onClick={remove}
              disabled={busy !== null}
              className="text-sm text-danger hover:underline underline-offset-4 disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        )}

        <div className="flex items-center gap-3">
          <select
            value={deck}
            onChange={(e) => setDeck(e.target.value)}
            aria-label="Deck"
            className="field flex-1 min-w-0"
          >
            {deckOptions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button onClick={onClose} className="btn-quiet px-1">
            Cancel
          </button>
          <button onClick={save} disabled={busy !== null} className="btn-primary">
            {busy === "save" ? "Saving…" : appendTo ? `Add to ${appendTo.lemma}` : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
