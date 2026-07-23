"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Book, type FeedFetchResult } from "@/lib/api";
import { GeneralScoreLine, ScoreLine } from "@/lib/score-display";

export default function QueuePage() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<FeedFetchResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Quick title translation so an unfamiliar candidate can be judged at a glance.
  const [titleTx, setTitleTx] = useState<Record<number, string>>({});
  const [txId, setTxId] = useState<number | null>(null);

  const refresh = () => {
    api
      .listBooks({ status: "candidate" })
      .then(setBooks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the queue."));
  };

  useEffect(refresh, []);

  const fetchNew = async () => {
    setFetching(true);
    setFetchError(null);
    setFetchResult(null);
    try {
      setFetchResult(await api.fetchFeeds());
      refresh();
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Fetch failed.");
    } finally {
      setFetching(false);
    }
  };

  const translateTitle = async (book: Book) => {
    setTxId(book.id);
    try {
      const r = await api.translate(book.title);
      setTitleTx((prev) => ({ ...prev, [book.id]: r.translation }));
    } catch (e) {
      setTitleTx((prev) => ({
        ...prev,
        [book.id]: e instanceof Error ? `(${e.message})` : "(translation failed)",
      }));
    } finally {
      setTxId(null);
    }
  };

  const decide = async (id: number, status: "library" | "discarded") => {
    setBusyId(id);
    try {
      await api.patchBook(id, { status });
      setBooks((prev) => prev?.filter((b) => b.id !== id) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update item.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Link href="/" className="text-sm text-muted hover:text-ink transition-colors">
          ← Library
        </Link>
        <Link href="/feeds" className="text-sm text-muted hover:text-ink transition-colors">
          Manage feeds
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-serif">Queue</h1>
        <button
          onClick={fetchNew}
          disabled={fetching}
          className="rounded-full bg-accent text-accent-ink px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {fetching ? "Fetching…" : "Fetch new candidates"}
        </button>
      </div>

      {fetchError && <p className="text-danger text-sm">{fetchError}</p>}

      {fetchResult && (
        <div className="rounded-xl border border-border bg-surface shadow-sm p-4 text-sm flex flex-col gap-1">
          <p>
            Checked <b>{fetchResult.checked_feeds}</b> feed(s), created{" "}
            <b>{fetchResult.candidates_created}</b> new candidate(s)
            {fetchResult.skipped_feed_types > 0 && (
              <>
                , skipped <b>{fetchResult.skipped_feed_types}</b> unsupported feed type(s)
              </>
            )}
            .
          </p>
          {fetchResult.feeds.some((f) => f.fetch_error) && (
            <ul className="list-disc list-inside text-danger">
              {fetchResult.feeds
                .filter((f) => f.fetch_error)
                .map((f) => (
                  <li key={f.id}>
                    {f.name}: {f.fetch_error}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      {error && <p className="text-danger text-sm">{error}</p>}

      {books === null && !error && <p className="text-muted">Loading…</p>}

      {books?.length === 0 && (
        <p className="text-muted">
          No candidates waiting. Try &quot;Fetch new candidates&quot;.
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {books?.map((book) => (
          <li
            key={book.id}
            className="rounded-xl border border-border bg-surface p-4 shadow-sm flex flex-col gap-2"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium">{book.title}</span>
                <button
                  onClick={() => translateTitle(book)}
                  disabled={txId === book.id}
                  className="shrink-0 text-xs text-muted hover:text-ink transition-colors disabled:opacity-50"
                >
                  {txId === book.id ? "…" : "Translate"}
                </button>
              </div>
              {titleTx[book.id] && (
                <p className="text-sm text-accent mt-0.5">{titleTx[book.id]}</p>
              )}
              <div className="text-xs text-muted mt-0.5">
                {[book.source, book.topic, ...book.tags].filter(Boolean).join(" · ")}
              </div>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <ScoreLine book={book} />
              <GeneralScoreLine book={book} />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => decide(book.id, "discarded")}
                disabled={busyId === book.id}
                className="px-3 py-1.5 text-sm rounded-full border border-danger-soft text-danger hover:bg-danger/10 transition-colors disabled:opacity-50"
              >
                Discard
              </button>
              <button
                onClick={() => decide(book.id, "library")}
                disabled={busyId === book.id}
                className="px-4 py-2 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                Promote
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
