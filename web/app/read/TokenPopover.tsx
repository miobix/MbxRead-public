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

// Epic 22: dictionary-derived chips run strong→pale across this "blue family" in
// the order they're added this session (front forms + back senses, combined).
const DICT_SHADES = ["bg-dict-1", "bg-dict-2", "bg-dict-3", "bg-dict-4"];
const dictShade = (i: number) => DICT_SHADES[Math.min(i, DICT_SHADES.length - 1)];

const LEMMA_GROUP = "";

export function TokenPopover({
  target,
  bookId,
  pageNo,
  decks,
  defaultDeck,
  translatorBackend,
  hanjaMode,
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
  // Epic 25: on-demand hanja saves (from /terms' "Add word") show an editable
  // Hanja field and route it into the create/patch payload. Also turns on when
  // editing a term that already has one, so it stays editable after the fact.
  hanjaMode?: boolean;
  onClose: () => void;
  onSaved: (term: Term) => void;
  onDeleted: (term: TermSummary) => void;
}) {
  const isEditing = target.existing !== null;
  // Phrases are translate-only: dictionary, forms, and the manual front-entry
  // affordance all hide, since a multi-word span has no single dictionary lemma or
  // card-worthy forms.
  const isPhrase = target.isPhrase;
  // The select must always include whatever deck the save will actually use —
  // the term's current deck when editing, and the popover's defaultDeck (e.g.
  // Epic 25's hanja_deck) when adding new, neither of which is necessarily one
  // of the user's regular `decks`.
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
  const [hanja, setHanja] = useState(target.existing?.hanja ?? "");
  const showHanja = hanjaMode || !!target.existing?.hanja;
  const [dictEntries, setDictEntries] = useState<DictEntry[] | null>(null);
  const [manualFront, setManualFront] = useState("");
  const [manualBack, setManualBack] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"translate" | "dict" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A term never touched by this card builder (no back_items) shows its old flat
  // translation read-only instead of chips — no migration forced (Epic 22).
  const legacyTranslation =
    (target.existing?.back_items.length ?? 0) === 0 ? target.existing?.translation || "" : "";

  const groupKeyFor = (text: string) => (text === lemma.trim() ? LEMMA_GROUP : text);

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
    // The click is the homograph disambiguation — overwrite whatever was there.
    if (entry.origin) setHanja(entry.origin);
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

  const addPhraseBackText = (text: string) => {
    const value = text.trim();
    if (!value) return;
    setBackItems((prev) => {
      if (prev.some((b) => b.group === LEMMA_GROUP && b.kind === "manual" && b.text === value)) {
        return prev;
      }
      return [...prev, { group: LEMMA_GROUP, kind: "manual", text: value, korean_def: "" }];
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
    // Only send back_items when there's actually structured content — an empty
    // array would otherwise blank out a legacy term's flat translation on any
    // save (e.g. just changing the deck) via the server's derived-mirror rule.
    const backItemsPayload = backItems.length > 0 ? backItems : undefined;
    // Never send hanja from a plain reading-flow save — only /terms' hanjaMode
    // (or editing a term that already has one) touches this field.
    const hanjaPayload = showHanja ? hanja.trim() : undefined;
    try {
      const term = target.existing
        ? await api.patchTerm(target.existing.id, {
            lemma: trimmedLemma,
            deck,
            sentence: target.sentence,
            notes,
            forms,
            back_items: backItemsPayload,
            hanja: hanjaPayload,
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
            // Provenance: record where this word was first saved (Epic 16 stats).
            source_book_id: bookId ?? undefined,
            source_page: pageNo ?? undefined,
            hanja: hanjaPayload,
          });
      onSaved(term);
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

  const backItemsFor = (group: string) => backItems.filter((b) => b.group === group);
  const backIndexOf = (item: BackItem) => backItems.indexOf(item);

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

        {showHanja && (
          <input
            value={hanja}
            onChange={(e) => setHanja(e.target.value)}
            placeholder="Hanja"
            className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
          />
        )}

        <div className="flex gap-3 flex-wrap justify-center">
          <button
            onClick={translateWord}
            disabled={busy !== null}
            className="px-5 py-2.5 text-base rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
          >
            {busy === "translate" ? "Translating…" : "Translate"}
          </button>
          {!isPhrase && (
            <button
              onClick={lookupDictionary}
              disabled={busy !== null}
              className="px-5 py-2.5 text-base rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
            >
              {busy === "dict" ? "Looking up…" : "Dictionary"}
            </button>
          )}
        </div>

        {target.sentence && <p className="text-xs text-muted italic">{target.sentence}</p>}

        {/* Front → Back preview — a true WYSIWYG of what syncs to Anki. One row
            per front entry so it's immediately visible which word each Back chip
            belongs to, instead of two same-height-assuming parallel columns. */}
        <div className="flex flex-col divide-y divide-border border-t border-b border-border text-xs">
          {legacyTranslation && (
            <div className="py-1.5 text-muted italic">(legacy) {legacyTranslation}</div>
          )}
          {frontEntries.map((entry, i) => {
            const group = i === 0 ? LEMMA_GROUP : entry.text;
            const items = backItemsFor(group);
            return (
              <div key={i} className="py-1.5 flex flex-wrap items-center gap-1.5">
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 shrink-0 ${chipClass(
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
                {items.length > 0 && <span className="text-muted">→</span>}
                {items.map((item) => {
                  const bi = backIndexOf(item);
                  return (
                    <span
                      key={bi}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${chipClass(
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
              </div>
            );
          })}
        </div>

        {!isPhrase && dictEntries && (
          <div className="flex flex-col gap-2 max-h-52 overflow-y-auto border-t border-border pt-2">
            {dictEntries.length === 0 && (
              <p className="text-xs text-muted">No dictionary entries found.</p>
            )}
            {dictEntries.map((entry, i) => (
              <div key={i} className="text-xs">
                <button
                  type="button"
                  onClick={() => addDictHeadword(entry)}
                  className="font-medium text-accent hover:underline"
                  title="Add as a highlighted form + first definition"
                >
                  {entry.word}
                </button>{" "}
                {entry.origin && <span className="text-muted">{entry.origin}</span>}{" "}
                <span className="text-muted">{entry.pos}</span>
                <ul className="mt-0.5 flex flex-col gap-0.5">
                  {entry.definitions.map((d, j) => (
                    <li key={j}>
                      <button
                        type="button"
                        onClick={() =>
                          addDictSense(groupKeyFor(entry.word.trim()), d, entry.examples[0])
                        }
                        className="text-left text-muted hover:text-ink transition-colors"
                        title="Add this definition to Back"
                      >
                        <b>{d.en_word}</b>
                        {d.en_def ? ` — ${d.en_def}` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* Examples — the literal content of the Anki "Examples" field. */}
        <div className="flex flex-col gap-1 border-t border-border pt-2">
          <span className="text-[11px] uppercase tracking-wide text-muted">Examples</span>
          {backItems
            .map((item, i) => ({ item, i }))
            .filter(({ item }) => item.kind === "dict" && item.korean_def)
            .map(({ item, i }) => (
              <div key={i} className="flex items-start gap-1 text-xs">
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
            placeholder="Notes…"
            rows={2}
            className="mt-1 rounded-lg border border-border bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
          />
        </div>

        {/* Add entry — hand-typed content that never came from Translate/Dictionary.
            Always its own independent group (front), never merged into the lemma. */}
        <div className="flex flex-col gap-1.5 border-t border-border pt-2">
          <span className="text-[11px] uppercase tracking-wide text-muted">Add entry</span>
          {isPhrase ? (
            <div className="flex gap-1.5">
              <input
                value={manualBack}
                onChange={(e) => setManualBack(e.target.value)}
                placeholder="Add a translation"
                className="flex-1 rounded-lg border border-border bg-transparent px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              />
              <button
                type="button"
                onClick={() => {
                  addPhraseBackText(manualBack);
                  setManualBack("");
                }}
                className="px-3 py-1.5 text-xs rounded-full border border-border hover:border-accent transition-colors"
              >
                Add
              </button>
            </div>
          ) : (
            <>
              <div className="flex gap-1.5">
                <input
                  value={manualFront}
                  onChange={(e) => {
                    setManualFront(e.target.value);
                    setManualError(null);
                  }}
                  placeholder="Front"
                  className="flex-1 rounded-lg border border-border bg-transparent px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
                />
                <input
                  value={manualBack}
                  onChange={(e) => setManualBack(e.target.value)}
                  placeholder="Back"
                  className="flex-1 rounded-lg border border-border bg-transparent px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
                />
                <button
                  type="button"
                  onClick={addManualEntry}
                  className="px-3 py-1.5 text-xs rounded-full border border-border hover:border-accent transition-colors"
                >
                  Add
                </button>
              </div>
              {manualError && <p className="text-danger text-xs">{manualError}</p>}
            </>
          )}
        </div>

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
            {target.existing?.status !== "learning" && (
              <button
                onClick={() => setStatus("learning")}
                disabled={busy !== null}
                className="px-3 py-1.5 rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
              >
                Mark learning
              </button>
            )}
            {target.existing?.status !== "known" && (
              <button
                onClick={() => setStatus("known")}
                disabled={busy !== null}
                className="px-3 py-1.5 rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
              >
                Mark known
              </button>
            )}
            {target.existing?.status !== "ignored" && (
              <button
                onClick={() => setStatus("ignored")}
                disabled={busy !== null}
                className="px-3 py-1.5 rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
              >
                Ignore
              </button>
            )}
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
