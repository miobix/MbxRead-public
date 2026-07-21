"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";

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
      <Link href="/" className="text-sm text-zinc-500 self-start">
        ← Books
      </Link>

      <h1 className="text-2xl font-semibold">Settings</h1>

      {error && <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>}

      {!settings && !error && <p className="text-zinc-500">Loading…</p>}

      {settings && (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-zinc-500">Decks</h2>
            <ul className="flex flex-col gap-2">
              {settings.decks.map((deck) => (
                <li
                  key={deck}
                  className="flex items-center justify-between rounded-lg border border-zinc-200 dark:border-zinc-800 px-3 py-2 text-sm"
                >
                  <span>
                    {deck}
                    {deck === settings.default_deck && (
                      <span className="ml-2 text-xs text-zinc-500">(default)</span>
                    )}
                  </span>
                  <button
                    onClick={() => removeDeck(deck)}
                    disabled={saving}
                    className="text-red-600 dark:text-red-400 text-xs disabled:opacity-50"
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
                className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm"
              />
              <button
                onClick={addDeck}
                disabled={saving || !newDeck.trim()}
                className="px-4 py-2 text-sm rounded-full border border-zinc-300 dark:border-zinc-700 disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-zinc-500">Default deck</h2>
            <select
              value={settings.default_deck}
              onChange={(e) => save({ ...settings, default_deck: e.target.value })}
              disabled={saving || settings.decks.length === 0}
              className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm"
            >
              {settings.decks.map((deck) => (
                <option key={deck} value={deck}>
                  {deck}
                </option>
              ))}
            </select>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-zinc-500">Translator backend</h2>
            <select
              value={settings.translator_backend}
              onChange={(e) =>
                save({ ...settings, translator_backend: e.target.value as Settings["translator_backend"] })
              }
              disabled={saving}
              className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm"
            >
              <option value="deepl">DeepL</option>
              <option value="claude">Claude</option>
            </select>
          </section>

          {saved && !saving && <p className="text-sm text-zinc-500">Saved.</p>}
        </>
      )}
    </main>
  );
}
