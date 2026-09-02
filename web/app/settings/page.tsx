"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";
import {
  MAX_LINES,
  MIN_LINES,
  setReaderLines,
  useReaderLines,
} from "@/lib/reader-lines";


export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [newDeck, setNewDeck] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const lines = useReaderLines();

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load settings."));
  }, []);

  const save = async (next: Settings) => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      setSettings(await api.putSettings(next));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const addDeck = () => {
    if (!settings) return;
    const name = newDeck.trim();
    if (!name || settings.decks.includes(name)) return;
    setNewDeck("");
    save({ ...settings, decks: [...settings.decks, name] });
  };

  const removeDeck = (name: string) => {
    if (!settings) return;
    const decks = settings.decks.filter((d) => d !== name);
    const default_deck = settings.default_deck === name ? (decks[0] ?? "") : settings.default_deck;
    save({ ...settings, decks, default_deck });
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      <h1 className="text-2xl font-semibold font-serif">Settings</h1>

      {error && <p className="text-danger text-sm">{error}</p>}

      {!settings && !error && <p className="text-muted">Loading…</p>}

      {settings && (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">Decks</h2>
            <ul className="flex flex-col gap-2">
              {settings.decks.map((deck) => (
                <li
                  key={deck}
                  className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                >
                  <span>
                    {deck}
                    {deck === settings.default_deck && (
                      <span className="ml-2 text-xs text-muted">(default)</span>
                    )}
                  </span>
                  <button
                    onClick={() => removeDeck(deck)}
                    disabled={saving}
                    className="text-danger text-xs hover:underline disabled:opacity-50"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>

            <div className="flex gap-2">
              <input
                value={newDeck}
                onChange={(e) => setNewDeck(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addDeck();
                }}
                placeholder="New deck name"
                className="flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              />
              <button
                onClick={addDeck}
                disabled={saving || !newDeck.trim()}
                className="px-4 py-2 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">Default deck</h2>
            <select
              value={settings.default_deck}
              onChange={(e) => save({ ...settings, default_deck: e.target.value })}
              disabled={saving || settings.decks.length === 0}
              className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            >
              {settings.decks.map((deck) => (
                <option key={deck} value={deck}>
                  {deck}
                </option>
              ))}
            </select>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">Hanja deck</h2>
            <p className="text-xs text-muted">
              Anki deck for on-demand hanja saves (Terms → Add word), kept separate from
              your regular reading decks and from your character-review Hanja deck.
            </p>
            <input
              value={settings.hanja_deck}
              onChange={(e) => setSettings({ ...settings, hanja_deck: e.target.value })}
              onBlur={() => save(settings)}
              disabled={saving}
              className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            />
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">Translator backend</h2>
            <select
              value={settings.translator_backend}
              onChange={(e) =>
                save({ ...settings, translator_backend: e.target.value as Settings["translator_backend"] })
              }
              disabled={saving}
              className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            >
              <option value="deepl">DeepL</option>
              <option value="claude">Claude</option>
            </select>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">
              Lines per page{" "}
              <span className="font-normal text-xs">· this device only</span>
            </h2>
            <p className="text-xs text-muted">
              Exactly how many lines of text one reader page holds. The browser breaks
              the page after this many real lines, so it&apos;s never more or less than
              you ask for. Stored on this device, not on the server — your phone fits
              fewer characters per line than a laptop, so each one wants its own value.
            </p>
            <label className="flex items-center gap-2 text-sm mt-1">
              <span className="text-muted shrink-0">Lines</span>
              <input
                type="number"
                min={MIN_LINES}
                max={MAX_LINES}
                value={lines}
                onChange={(e) => setReaderLines(Number(e.target.value))}
                className="w-20 rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              />
            </label>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted">Queue candidate retention</h2>
            <p className="text-xs text-muted">
              How many days an unpromoted, undiscarded item sits in the Queue before the
              fetch job automatically discards it.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={90}
                value={settings.candidate_retention_days}
                onChange={(e) => {
                  const days = Number(e.target.value);
                  if (Number.isFinite(days) && days >= 1 && days <= 90) {
                    save({ ...settings, candidate_retention_days: days });
                  }
                }}
                disabled={saving}
                className="w-20 rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              />
              <span className="text-sm text-muted">days</span>
            </div>
          </section>

          {saving && <p className="text-sm text-muted">Saving…</p>}
          {saved && !saving && <p className="text-sm text-accent">Saved.</p>}
        </>
      )}
    </main>
  );
}
