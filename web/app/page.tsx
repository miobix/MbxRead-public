"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Book, type BookSort } from "@/lib/api";
import { SourceChip } from "@/lib/chips";
import { GeneralScoreLine, ScoreLine } from "@/lib/score-display";
import { SOURCES, TOPICS } from "@/lib/topics";
import { AddBookSheet, EditBookSheet } from "./LibrarySheets";

// One extra row beyond the page size tells us "there's more" without a count endpoint.
const PAGE_SIZE = 30;

const SORTS: { key: BookSort; label: string }[] = [
  { key: "opened", label: "Recently opened" },
  { key: "recent", label: "Recently added" },
  { key: "easiest", label: "Easiest unread" },
];

const NAV_LINKS = [
  { href: "/queue", label: "Queue" },
  { href: "/stats", label: "Stats" },
  { href: "/feeds", label: "Feeds" },
  { href: "/terms", label: "Terms" },
  { href: "/settings", label: "Settings" },
] as const;

/** Mobile-only nav. Below `sm` the five inline links crowd out "+ Add", so they
 *  collapse behind a hamburger; at `sm` and up this is hidden and the inline links
 *  render instead, leaving the desktop header untouched. Bars are drawn with plain
 *  spans rather than an icon dependency — the app ships no icon library. */
function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative sm:hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Menu"
        aria-expanded={open}
        className="flex flex-col justify-center gap-1 rounded border border-border px-2.5 py-2.5 text-muted hover:text-ink hover:border-accent transition-colors"
      >
        <span className="block h-0.5 w-4 rounded-full bg-current" />
        <span className="block h-0.5 w-4 rounded-full bg-current" />
        <span className="block h-0.5 w-4 rounded-full bg-current" />
      </button>
      {open && (
        <>
          {/* Invisible full-screen catcher so a tap anywhere else dismisses the menu. */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <nav className="absolute right-0 top-full z-50 mt-2 w-40 overflow-hidden rounded border border-border bg-surface shadow-lg">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="block px-4 py-2.5 text-sm text-muted hover:bg-paper hover:text-ink transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </>
      )}
    </div>
  );
}

export default function HomePage() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [sort, setSort] = useState<BookSort>("opened");
  const [scoring, setScoring] = useState<number | null>(null);
  const [topicFilter, setTopicFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [editing, setEditing] = useState<Book | null>(null);

  const activeFilters = [topicFilter, sourceFilter, showArchived].filter(Boolean).length;

  const refresh = () => {
    api
      .listBooks({
        topic: topicFilter || undefined,
        source: sourceFilter || undefined,
        archived: showArchived,
        sort,
        limit: PAGE_SIZE + 1,
        offset: 0,
      })
      .then((result) => {
        setHasMore(result.length > PAGE_SIZE);
        setBooks(result.slice(0, PAGE_SIZE));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load your library."));
  };

  useEffect(refresh, [topicFilter, sourceFilter, showArchived, sort]);

  const loadMore = async () => {
    if (!books) return;
    setLoadingMore(true);
    try {
      const result = await api.listBooks({
        topic: topicFilter || undefined,
        source: sourceFilter || undefined,
        archived: showArchived,
        sort,
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

  const score = async (id: number) => {
    setScoring(id);
    try {
      const updated = await api.scoreBook(id);
      setBooks((prev) => prev?.map((b) => (b.id === id ? updated : b)) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to score item.");
    } finally {
      setScoring(null);
    }
  };

  // Re-fetches (rather than patching local state) since toggling archived/read
  // can move a book out of the current filter view.
  const toggle = async (id: number, field: "archived" | "read", value: boolean) => {
    try {
      await api.patchBook(id, { [field]: value });
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update item.");
    }
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="page-title">Library</h1>
        <div className="flex items-center gap-3">
          <nav className="hidden sm:flex items-center gap-3">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-muted hover:text-ink transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <button onClick={() => setModalOpen(true)} className="btn-primary">
            Add text
          </button>
          <MobileNav />
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 text-sm">
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as BookSort)}
          aria-label="Sort"
          className="field py-1.5"
        >
          {SORTS.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => setFiltersOpen((o) => !o)}
          aria-expanded={filtersOpen}
          className={`btn-secondary py-1.5 ${activeFilters ? "border-accent" : ""}`}
        >
          Filters
          {activeFilters > 0 && (
            <span className="rounded bg-accent px-1.5 text-xs font-semibold text-accent-ink tabular-nums">
              {activeFilters}
            </span>
          )}
        </button>
      </div>

      {filtersOpen && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border border-border bg-surface p-4 text-sm">
          <label className="flex items-center gap-2 text-muted">
            Topic
            <select
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="field px-2 py-1"
            >
              <option value="">All</option>
              {TOPICS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-muted">
            Source
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="field px-2 py-1"
            >
              <option value="">All</option>
              {SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-muted">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="accent-accent"
            />
            Show archived
          </label>
        </div>
      )}

      {error && <p className="text-danger text-sm">{error}</p>}

      {books === null && !error && <p className="text-muted">Loading…</p>}

      {books?.length === 0 && (
        <p className="text-muted">Nothing matches. Add a text or change the filters.</p>
      )}

      <ul className="flex flex-col gap-3">
        {books?.map((book) => {
          const pct =
            book.current_offset > 0 && book.total_chars > 0
              ? Math.min(100, Math.round((book.current_offset / book.total_chars) * 100))
              : 0;
          const href = `/read/?id=${book.id}`;
          return (
            <li
              key={book.id}
              className="rounded-lg border border-border bg-surface p-4 flex flex-col gap-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted">
                  <SourceChip source={book.source} />
                  {[book.topic, ...book.tags].filter(Boolean).map((t) => (
                    <span key={t}>{t}</span>
                  ))}
                </div>
                <BookMenu
                  open={menuFor === book.id}
                  onToggle={() => setMenuFor((id) => (id === book.id ? null : book.id))}
                  onClose={() => setMenuFor(null)}
                  items={[
                    {
                      label: book.scored_at ? "Rescore difficulty" : "Score difficulty",
                      onSelect: () => score(book.id),
                    },
                    {
                      label: book.read ? "Mark unread" : "Mark read",
                      onSelect: () => toggle(book.id, "read", !book.read),
                    },
                    { label: "Edit details", onSelect: () => setEditing(book) },
                    ...(book.source_url
                      ? [{ label: "Open source ↗", href: book.source_url }]
                      : []),
                    {
                      label: book.archived ? "Restore" : "Archive",
                      onSelect: () => toggle(book.id, "archived", !book.archived),
                    },
                  ]}
                />
              </div>

              <Link
                href={href}
                className="-mt-1 text-[17px] font-semibold leading-snug [word-break:keep-all] hover:text-accent transition-colors"
              >
                {book.title}
              </Link>

              {/* A percentage, not a page number: pages are per-device. */}
              <div className="flex items-center gap-3">
                <div className="h-1 flex-1 rounded-full bg-line">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                </div>
                <span className="w-20 text-right text-xs text-muted tabular-nums">
                  {book.read ? "Finished" : pct > 0 ? `${pct}% read` : "Not started"}
                </span>
              </div>

              <div className="flex items-end justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-0.5">
                  {book.scored_at ? (
                    <>
                      <ScoreLine book={book} />
                      <GeneralScoreLine book={book} />
                    </>
                  ) : (
                    <button
                      onClick={() => score(book.id)}
                      disabled={scoring === book.id}
                      className="btn-link self-start text-xs"
                    >
                      {scoring === book.id ? "Scoring…" : "Score difficulty"}
                    </button>
                  )}
                </div>
                <Link href={href} className="btn-primary shrink-0 py-1.5">
                  {book.read ? "Read again" : pct > 0 ? "Continue" : "Start"}
                </Link>
              </div>
            </li>
          );
        })}
      </ul>

      {hasMore && (
        <button onClick={loadMore} disabled={loadingMore} className="btn-secondary w-full">
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}

      {modalOpen && (
        <AddBookSheet
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            refresh();
          }}
        />
      )}

      {editing && (
        <EditBookSheet
          book={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}
    </main>
  );
}

type MenuItem = { label: string; onSelect?: () => void; href?: string };

/** Per-card "⋯" menu. Archive sits last and behind a tap, away from the title. */
function BookMenu({
  open,
  onToggle,
  onClose,
  items,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  items: MenuItem[];
}) {
  const itemClass =
    "block w-full px-4 py-2.5 text-left text-sm text-ink hover:bg-paper transition-colors";
  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={onToggle}
        aria-label="More actions"
        aria-expanded={open}
        className="-mr-1.5 -mt-1 rounded px-1.5 py-0.5 text-lg leading-none text-muted hover:text-ink transition-colors"
      >
        ⋯
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={onClose} aria-hidden />
          <div className="absolute right-0 top-full z-50 mt-1 w-48 overflow-hidden rounded border border-border bg-surface shadow-lg">
            {items.map((item) =>
              item.href ? (
                <a
                  key={item.label}
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onClose}
                  className={itemClass}
                >
                  {item.label}
                </a>
              ) : (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => {
                    onClose();
                    item.onSelect?.();
                  }}
                  className={itemClass}
                >
                  {item.label}
                </button>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}
