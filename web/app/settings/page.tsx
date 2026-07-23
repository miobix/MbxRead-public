"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";

const PAGE_SIZE_PRESETS = [
  { label: "Short", chars: 450 },
  { label: "Medium", chars: 650 },
  { label: "Long", chars: 1200 },
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
        ← Books
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
              How much text fits on one reader page. Smaller pages scroll less on a phone.
              Changing this re-paginates your whole library (and resets pages-read counts).
            </p>
            <div className="flex gap-2">
              {PAGE_SIZE_PRESETS.map((p) => (
                <button
                  key={p.chars}
                  onClick={() => save({ ...settings, page_size: p.chars })}
                  disabled={saving}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50 ${
                    settings.page_size === p.chars
                      ? "border-accent text-ink font-medium"
                      : "border-border text-muted hover:border-accent"
                  }`}
                >
                  {p.label}
                  <span className="block text-xs text-muted">{p.chars} chars</span>
                </button>
              ))}
            </div>
          </section>

          {saving && <p className="text-sm text-muted">Saving…</p>}
          {saved && !saving && <p className="text-sm text-accent">Saved.</p>}
        </>
      )}
    </main>
  );
}
