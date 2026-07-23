"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Feed, type FeedType } from "@/lib/api";
import { FEED_TYPES, TOPICS } from "@/lib/topics";

const BLANK = { name: "", type: "youtube" as FeedType, url_or_channel_id: "", topic: "gaming" };

// YouTube feeds store the bare channel id (UC…); RSS/scraper store a full URL.
const idHint = (type: FeedType) =>
  type === "youtube" ? "Channel id (UC…)" : "Feed URL";

export default function FeedsPage() {
  const [feeds, setFeeds] = useState<Feed[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Partial<Feed>>({});
  const [adding, setAdding] = useState(false);
  const [newFeed, setNewFeed] = useState(BLANK);

  const refresh = () => {
    api
      .listFeeds()
      .then(setFeeds)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load feeds."));
  };

  useEffect(refresh, []);

  const toggle = async (feed: Feed) => {
    setBusyId(feed.id);
    try {
      const updated = await api.patchFeed(feed.id, { enabled: !feed.enabled });
      setFeeds((prev) => prev?.map((f) => (f.id === feed.id ? updated : f)) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update feed.");
    } finally {
      setBusyId(null);
    }
  };

  const saveEdit = async (id: number) => {
    setBusyId(id);
    try {
      const updated = await api.patchFeed(id, {
        name: draft.name,
        type: draft.type,
        url_or_channel_id: draft.url_or_channel_id,
        topic: draft.topic,
      });
      setFeeds((prev) => prev?.map((f) => (f.id === id ? updated : f)) ?? prev);
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save feed.");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: number) => {
    setBusyId(id);
    try {
      await api.deleteFeed(id);
      setFeeds((prev) => prev?.filter((f) => f.id !== id) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete feed.");
    } finally {
      setBusyId(null);
    }
  };

  const add = async () => {
    if (!newFeed.name.trim() || !newFeed.url_or_channel_id.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await api.createFeed(newFeed);
      setNewFeed(BLANK);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add feed.");
    } finally {
      setAdding(false);
    }
  };

  const inputCls =
    "rounded-lg border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors";

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      <div>
        <h1 className="text-2xl font-semibold font-serif">Feeds</h1>
        <p className="text-sm text-muted mt-1">
          Content sources the fetch job pulls into the{" "}
          <Link href="/queue" className="underline hover:text-ink">
            Queue
          </Link>
          . Add, edit, or turn any off.
        </p>
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}
      {feeds === null && !error && <p className="text-muted">Loading…</p>}

      <ul className="flex flex-col gap-2">
        {feeds?.map((feed) =>
          editingId === feed.id ? (
            <li
              key={feed.id}
              className="rounded-xl border border-accent bg-surface p-3 shadow-sm flex flex-col gap-2"
            >
              <input
                className={inputCls}
                value={draft.name ?? ""}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="Name"
              />
              <div className="flex gap-2">
                <select
                  className={inputCls}
                  value={draft.type}
                  onChange={(e) => setDraft({ ...draft, type: e.target.value as FeedType })}
                >
                  {FEED_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <select
                  className={`${inputCls} flex-1`}
                  value={draft.topic}
                  onChange={(e) => setDraft({ ...draft, topic: e.target.value })}
                >
                  {TOPICS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <input
                className={inputCls}
                value={draft.url_or_channel_id ?? ""}
                onChange={(e) => setDraft({ ...draft, url_or_channel_id: e.target.value })}
                placeholder={idHint(draft.type ?? "rss")}
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setEditingId(null)}
                  className="px-3 py-1.5 text-sm rounded-full border border-border hover:border-accent transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => saveEdit(feed.id)}
                  disabled={busyId === feed.id}
                  className="px-4 py-1.5 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </li>
          ) : (
            <li
              key={feed.id}
              className={`rounded-xl border border-border bg-surface p-3 shadow-sm flex items-center justify-between gap-3 ${
                feed.enabled ? "" : "opacity-60"
              }`}
            >
              <div className="min-w-0">
                <div className="font-medium truncate">{feed.name}</div>
                <div className="text-xs text-muted truncate">
                  {[feed.type, feed.topic].filter(Boolean).join(" · ")}
                </div>
                <div className="text-xs text-muted/70 truncate">{feed.url_or_channel_id}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => toggle(feed)}
                  disabled={busyId === feed.id}
                  className={`px-2.5 py-1 text-xs rounded-full border transition-colors disabled:opacity-50 ${
                    feed.enabled
                      ? "border-accent text-ink"
                      : "border-border text-muted hover:border-accent"
                  }`}
                >
                  {feed.enabled ? "On" : "Off"}
                </button>
                <button
                  onClick={() => {
                    setEditingId(feed.id);
                    setDraft(feed);
                  }}
                  className="text-xs text-muted hover:text-ink transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => remove(feed.id)}
                  disabled={busyId === feed.id}
                  className="text-xs text-danger hover:underline disabled:opacity-50"
                >
                  Delete
                </button>
              </div>
            </li>
          )
        )}
      </ul>

      <section className="flex flex-col gap-2 rounded-xl border border-dashed border-border p-3 mt-2">
        <h2 className="text-sm font-medium text-muted">Add a feed</h2>
        <input
          className={inputCls}
          value={newFeed.name}
          onChange={(e) => setNewFeed({ ...newFeed, name: e.target.value })}
          placeholder="Name (e.g. 김성회의 G식백과)"
        />
        <div className="flex gap-2">
          <select
            className={inputCls}
            value={newFeed.type}
            onChange={(e) => setNewFeed({ ...newFeed, type: e.target.value as FeedType })}
          >
            {FEED_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            className={`${inputCls} flex-1`}
            value={newFeed.topic}
            onChange={(e) => setNewFeed({ ...newFeed, topic: e.target.value })}
          >
            {TOPICS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <input
          className={inputCls}
          value={newFeed.url_or_channel_id}
          onChange={(e) => setNewFeed({ ...newFeed, url_or_channel_id: e.target.value })}
          placeholder={idHint(newFeed.type)}
        />
        <button
          onClick={add}
          disabled={adding || !newFeed.name.trim() || !newFeed.url_or_channel_id.trim()}
          className="self-end px-4 py-2 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {adding ? "Adding…" : "Add feed"}
        </button>
      </section>
    </main>
  );
}
