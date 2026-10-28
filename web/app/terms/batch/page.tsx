"use client";

import { BackLink } from "@/lib/back-link";
import { useEffect, useState } from "react";
import { api, type HanjaListSection, type Settings } from "@/lib/api";
import { TokenPopover } from "../../read/TokenPopover";

type Word = HanjaListSection["words"][number];

export default function AddBatchPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [dates, setDates] = useState<string[] | null>(null);
  const [date, setDate] = useState("");
  const [sections, setSections] = useState<HanjaListSection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<Word | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {});
    api
      .hanjaLists()
      .then((d) => {
        setDates(d);
        setDate(d[0] ?? "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load word lists."));
  }, []);

  const load = (d: string) =>
    api
      .hanjaList(d)
      .then(setSections)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the word list."));

  useEffect(() => {
    if (date) load(date);
  }, [date]);

  const savedCount = sections?.flatMap((s) => s.words).filter((w) => w.status).length ?? 0;

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <BackLink href="/terms" label="Terms" />

      <h1 className="page-title">Add batch</h1>

      {dates?.length === 0 && <p className="text-muted">No /hanja-today lists yet.</p>}

      {dates && dates.length > 0 && (
        <select value={date} onChange={(e) => setDate(e.target.value)} className="field">
          {dates.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      )}

      {error && <p className="text-danger text-sm">{error}</p>}

      {savedCount > 0 && (
        <div className="rounded-lg border border-border bg-surface p-3 text-sm">
          {savedCount} word{savedCount > 1 && "s"} from this list already saved (same hanja).
        </div>
      )}

      {sections?.map((s) => (
        <section key={s.char} className="flex flex-col gap-2">
          <div>
            <h2 className="font-medium">{s.heading}</h2>
            {s.notes.map((n) => (
              <p key={n} className="text-xs text-muted">
                {n}
              </p>
            ))}
          </div>
          <ul className="flex flex-col gap-2">
            {s.words.map((w) => (
              <li
                key={`${w.word} ${w.hanja}`}
                className="rounded-lg border border-border bg-surface p-3 text-sm flex items-center justify-between gap-2"
              >
                <div>
                  <span className="font-medium">{w.word}</span>
                  <span className="text-muted"> {w.hanja}</span>
                  <div className="text-muted">
                    {w.meaning} · <span className="text-xs">{w.register}</span>
                  </div>
                </div>
                <button
                  onClick={() => setAdding(w)}
                  disabled={w.status !== null}
                  className="btn-primary shrink-0"
                >
                  {w.status === "anki" ? "In Anki" : w.status === "saved" ? "Saved" : "Add"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {adding && (
        <TokenPopover
          target={{ surface: adding.word, lemma: adding.word, sentence: "", isPhrase: false, existing: null }}
          bookId={null}
          pageNo={null}
          decks={settings?.decks ?? []}
          defaultDeck={settings?.hanja_deck || settings?.default_deck || ""}
          translatorBackend={settings?.translator_backend}
          hanjaMode
          hanjaDeck={settings?.hanja_deck}
          initialHanja={adding.hanja}
          autoLookup
          onClose={() => setAdding(null)}
          onSaved={() => load(date)}
          onDeleted={() => {}}
        />
      )}
    </main>
  );
}
