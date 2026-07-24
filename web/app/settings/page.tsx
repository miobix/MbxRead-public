"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";

const PAGE_ROWS_PRESETS = [
  { label: "Short", rows: 12 },
  { label: "Medium", rows: 22 },
  { label: "Long", rows: 40 },
] as const;

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [newDeck, setNewDeck] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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
            <h2 className="text-sm font-medium text-muted">Page size</h2>
            <p className="text-xs text-muted">
              How many visual rows fit on one reader page, estimated from line breaks
              and wrapping — so a page with lots of short lines (dialogue, subtitles)
              and a page of one long paragraph feel like similar amounts of reading.
              Changing this re-paginates your whole library (and resets pages-read counts).
            </p>
            <div className="flex gap-2">
              {PAGE_ROWS_PRESETS.map((p) => (
                <button
                  key={p.rows}
                  onClick={() => save({ ...settings, page_rows: p.rows })}
                  disabled={saving}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50 ${
                    settings.page_rows === p.rows
                      ? "border-accent text-ink font-medium"
                      : "border-border text-muted hover:border-accent"
                  }`}
                >
                  {p.label}
                  <span className="block text-xs text-muted">{p.rows} rows</span>
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm mt-1">
              <span className="text-muted shrink-0">Chars per row</span>
              <input
                type="number"
                min={10}
                max={120}
                value={settings.chars_per_row}
                onChange={(e) => {
                  const n = Number(e.target.value);
                  if (Number.isFinite(n) && n >= 10 && n <= 120) {
                    save({ ...settings, chars_per_row: n });
                  }
                }}
                disabled={saving}
                className="w-20 rounded-lg border border-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              />
            </label>
            <p className="text-xs text-muted">
              An estimate of how many characters fit on one line on your device — tune
              this once you&apos;re actually reading on your phone: too many rows per page
              means the estimate is too high, too few means it&apos;s too low.
            </p>
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
