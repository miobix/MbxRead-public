"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Book, type BookSort, type FeedFetchResult } from "@/lib/api";
import { SourceChip } from "@/lib/chips";
import { formatLength } from "@/lib/length";
import { GeneralScoreLine, ScoreLine } from "@/lib/score-display";
import { SOURCES, TOPICS } from "@/lib/topics";

type ViewMode = "cards" | "list";
type SortBy = "newest" | "easiest" | "shortest";

// UI labels stay as they were; "newest" maps to the API's "recent" (created-order)
// sort so pagination sorts correctly server-side instead of only within a page.
const SORT_TO_API: Record<SortBy, BookSort> = {
  newest: "recent",
  easiest: "easiest",
  shortest: "shortest",
};

const VIEW_MODE_KEY = "queueViewMode";
// See web/app/page.tsx's PAGE_SIZE comment — same "fetch one extra row" pattern.
const PAGE_SIZE = 30;

function formatTimestamp(ts: string | null): string {
  if (!ts) return "never";
  // Stored as SQLite's CURRENT_TIMESTAMP (UTC, no offset marker) — append "Z" so
  // the browser parses it as UTC and renders it in the reader's local time.
  return new Date(ts.replace(" ", "T") + "Z").toLocaleString();
}

export default function QueuePage() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<FeedFetchResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [lastFetchAttempt, setLastFetchAttempt] = useState<string | null>(null);

  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [sortBy, setSortBy] = useState<SortBy>("newest");
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [topicFilter, setTopicFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");

  // Quick title translation so an unfamiliar candidate can be judged at a glance.
  const [titleTx, setTitleTx] = useState<Record<number, string>>({});
  const [txId, setTxId] = useState<number | null>(null);

  const refresh = () => {
    api
      .listBooks({
        status: "candidate",
        topic: topicFilter || undefined,
        source: sourceFilter || undefined,
        sort: SORT_TO_API[sortBy],
        limit: PAGE_SIZE + 1,
        offset: 0,
      })
      .then((result) => {
        setHasMore(result.length > PAGE_SIZE);
        setBooks(result.slice(0, PAGE_SIZE));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the queue."));
  };

  useEffect(refresh, [topicFilter, sourceFilter, sortBy]);

  const loadMore = async () => {
    if (!books) return;
    setLoadingMore(true);
    try {
      const result = await api.listBooks({
        status: "candidate",
        topic: topicFilter || undefined,
        source: sourceFilter || undefined,
        sort: SORT_TO_API[sortBy],
        limit: PAGE_SIZE + 1,
        offset: books.length,
      });
      setHasMore(result.length > PAGE_SIZE);
      setBooks((prev) => [...(prev ?? []), ...result.slice(0, PAGE_SIZE)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more.");
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    api
      .getSettings()
      .then((s) => setLastFetchAttempt(s.last_fetch_attempt))
      .catch(() => {
        // best-effort — the timestamp line just stays hidden on failure
      });
  }, []);

  // View-mode preference persists across visits; read after mount (not in the
  // initial useState) so the static export's build-time render never touches
  // localStorage, and written back whenever the user flips it.
  useEffect(() => {
    const stored = localStorage.getItem(VIEW_MODE_KEY);
    if (stored === "cards" || stored === "list") setViewMode(stored);
  }, []);

  useEffect(() => {
    localStorage.setItem(VIEW_MODE_KEY, viewMode);
  }, [viewMode]);

  useEffect(() => {
    const onScroll = () => setShowBackToTop(window.scrollY > window.innerHeight * 2);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const fetchNew = async () => {
    setFetching(true);
    setFetchError(null);
    setFetchResult(null);
    try {
      setFetchResult(await api.fetchFeeds());
      refresh();
      api.getSettings().then((s) => setLastFetchAttempt(s.last_fetch_attempt));
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

      <p className="text-xs text-muted -mt-2">
        Last fetch attempt: {formatTimestamp(lastFetchAttempt)}
      </p>

      <div className="flex items-center flex-wrap gap-2 text-sm">
        <span className="text-muted">Topic:</span>
        <select
          value={topicFilter}
          onChange={(e) => setTopicFilter(e.target.value)}
          className="rounded-lg border border-border bg-transparent px-2 py-1 text-sm"
        >
          <option value="">All</option>
          {TOPICS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <span className="text-muted">Source:</span>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="rounded-lg border border-border bg-transparent px-2 py-1 text-sm"
        >
          <option value="">All</option>
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {fetchError && <p className="text-danger text-sm">{fetchError}</p>}

      {fetchResult && (
        <div className="rounded-xl border border-border bg-surface shadow-sm p-4 text-sm flex flex-col gap-1">
          <p>
            Checked <b>{fetchResult.checked_feeds}</b> feed(s), created{" "}
            <b>{fetchResult.candidates_created}</b> new candidate(s)
            {fetchResult.expired > 0 && (
              <>
                , expired <b>{fetchResult.expired}</b> stale candidate(s)
              </>
            )}
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

      {books && books.length > 0 && (
        <div className="flex items-center justify-between flex-wrap gap-2 text-sm">
          <div className="flex gap-1 rounded-lg bg-paper p-1">
            {(["cards", "list"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`rounded-md px-3 py-1 capitalize transition-colors ${
                  viewMode === mode
                    ? "bg-surface shadow-sm text-ink font-medium"
                    : "text-muted hover:text-ink"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted">Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortBy)}
              className="rounded-lg border border-border bg-transparent px-2 py-1 text-sm"
            >
              <option value="newest">Newest fetched</option>
              <option value="easiest">Easiest first</option>
              <option value="shortest">Shortest first</option>
            </select>
          </div>
        </div>
      )}

      <ul
        className={
          viewMode === "cards"
            ? "grid grid-cols-1 sm:grid-cols-2 gap-3"
            : "flex flex-col gap-3"
        }
      >
        {books?.map((book) => {
          const length = formatLength(book);
          return (
            <li
              key={book.id}
              className="rounded-xl border border-border bg-surface p-4 shadow-sm flex flex-col gap-2"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SourceChip source={book.source} />
                    {book.source_url && (
                      <a
                        href={book.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-muted hover:text-accent transition-colors"
                        title="Open source"
                      >
                        ↗
                      </a>
                    )}
                  </div>
                  <button
                    onClick={() => translateTitle(book)}
                    disabled={txId === book.id}
                    className="shrink-0 text-xs text-muted hover:text-ink transition-colors disabled:opacity-50"
                  >
                    {txId === book.id ? "…" : "Translate"}
                  </button>
                </div>
                <p className="font-medium mt-1">{book.title}</p>
                {titleTx[book.id] && (
                  <p className="text-sm text-accent mt-0.5">{titleTx[book.id]}</p>
                )}
                <div className="text-xs text-muted mt-0.5">
                  {[book.topic, ...book.tags].filter(Boolean).join(" · ")}
                  {length && <> · {length}</>}
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
          );
        })}
      </ul>

      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          className="rounded-lg border border-border py-2 text-sm text-muted hover:text-ink hover:bg-paper transition-colors disabled:opacity-50"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}

      {showBackToTop && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
          className="fixed bottom-6 right-6 w-11 h-11 rounded-full bg-accent text-accent-ink shadow-lg text-lg hover:opacity-90 transition-opacity"
        >
          ↑
        </button>
      )}
    </main>
  );
}
