"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type Book,
  type BookSort,
  type ScoreResult,
  type SubtitleImportResult,
} from "@/lib/api";
import { GeneralScoreLine, ScoreLine, coverageClass } from "@/lib/score-display";
import { SOURCES, TOPICS } from "@/lib/topics";

// 2026-07-24: fetch one extra row beyond the page size to detect "there's more"
// without a separate count endpoint — a plain array response stays backward
// compatible with every existing caller that omits limit/offset entirely.
const PAGE_SIZE = 30;

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
        className="flex flex-col justify-center gap-1 rounded-md border border-border px-2.5 py-2 text-muted hover:text-ink hover:border-accent transition-colors"
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
          <nav className="absolute right-0 top-full z-50 mt-2 w-36 overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
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
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold font-serif">MbxAndria</h1>
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Desktop keeps the inline links exactly as they were — the hamburger is
              a mobile-only addition, where five links plus "+ Add" no longer fit. */}
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
          <button
            onClick={() => setModalOpen(true)}
            className="rounded-md bg-accent text-accent-ink px-2.5 py-1.5 sm:px-4 sm:py-2 text-sm font-medium shadow-sm hover:opacity-90 transition-opacity"
          >
            + Add
          </button>
          <MobileNav />
        </div>
      </div>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}

      <div className="flex items-center flex-wrap gap-2 mb-3 text-sm">
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
        <label className="flex items-center gap-1 text-muted">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
      </div>

      {books === null && !error && <p className="text-muted">Loading…</p>}

      {books?.length === 0 && (
        <p className="text-muted">Nothing matches. Add something or adjust the filters.</p>
      )}

      {books && books.length > 0 && (
        <div className="flex items-center gap-2 mb-3 text-sm">
          <span className="text-muted">Sort:</span>
          <button
            onClick={() => setSort("opened")}
            className={sort === "opened" ? "text-ink font-medium" : "text-muted hover:text-ink"}
          >
            Recently opened
          </button>
          <span className="text-border">·</span>
          <button
            onClick={() => setSort("recent")}
            className={sort === "recent" ? "text-ink font-medium" : "text-muted hover:text-ink"}
          >
            Recently added
          </button>
          <span className="text-border">·</span>
          <button
            onClick={() => setSort("easiest")}
            className={sort === "easiest" ? "text-ink font-medium" : "text-muted hover:text-ink"}
          >
            Easiest unread
          </button>
        </div>
      )}

      <ul className="flex flex-col gap-3">
        {books?.map((book) => (
          <li
            key={book.id}
            className="flex gap-3 rounded-xl border border-border bg-surface p-4 shadow-sm"
          >
            {/* Actions live in their own column, off to the side of the card body:
                they used to sit inline under the title, where Archive was easy to
                hit by accident when reaching for the book itself. */}
            <div className="flex w-14 shrink-0 flex-col gap-1 text-center text-[10px] leading-tight">
              <button
                onClick={() => score(book.id)}
                disabled={scoring === book.id}
                title={book.scored_at ? "Re-score difficulty" : "Score difficulty"}
                className="rounded border border-border px-1 py-1.5 text-muted hover:text-ink hover:border-accent transition-colors disabled:opacity-50"
              >
                {scoring === book.id ? "…" : book.scored_at ? "rescore" : "score"}
              </button>
              <button
                onClick={() => toggle(book.id, "read", !book.read)}
                title={book.read ? "Mark unread" : "Mark read"}
                className="rounded border border-border px-1 py-1.5 text-muted hover:text-ink hover:border-accent transition-colors"
              >
                {book.read ? "unread" : "read"}
              </button>
              <button
                onClick={() => toggle(book.id, "archived", !book.archived)}
                title={book.archived ? "Restore from archive" : "Archive"}
                className="rounded border border-border px-1 py-1.5 text-muted hover:text-ink hover:border-accent transition-colors"
              >
                {book.archived ? "restore" : "archive"}
              </button>
            </div>

            <div className="min-w-0 flex-1">
              <Link
                href={`/read/?id=${book.id}`}
                className="block hover:text-accent transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{book.title}</span>
                  {(book.source === "pdf" || book.source === "epub") && (
                    <span className="text-xs text-muted border border-border rounded-full px-1.5">
                      Book
                    </span>
                  )}
                  {book.source === "subs" && (
                    <span className="text-xs text-muted border border-border rounded-full px-1.5">
                      Subs
                    </span>
                  )}
                  {book.read && <span className="text-xs text-accent">✓ read</span>}
                </div>
                {/* Progress as a percentage of the text, not a page number: pages are
                    per-device since Epic 24, and current_page no longer moves. */}
                <div className="text-sm text-muted">
                  {book.current_offset > 0 && book.total_chars > 0
                    ? `${Math.min(100, Math.round((book.current_offset / book.total_chars) * 100))}% read`
                    : "not started"}
                </div>
                {(book.topic || book.tags.length > 0) && (
                  <div className="text-xs text-muted mt-0.5">
                    {[book.topic, ...book.tags].filter(Boolean).join(" · ")}
                  </div>
                )}
              </Link>
              <div className="mt-2 flex items-center gap-3 flex-wrap">
                <ScoreLine book={book} />
                <GeneralScoreLine book={book} />
                {book.source_url && (
                  <a
                    href={book.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-muted hover:text-accent transition-colors"
                    title="Open source"
                  >
                    ↗ source
                  </a>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>

      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          className="mt-4 w-full rounded-lg border border-border py-2 text-sm text-muted hover:text-ink hover:bg-paper transition-colors disabled:opacity-50"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}

      {modalOpen && (
        <AddBookModal
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            refresh();
          }}
        />
      )}
    </main>
  );
}

type Mode = "paste" | "youtube" | "pdf" | "epub" | "subs" | "article";

const MODES: { key: Mode; label: string }[] = [
  { key: "paste", label: "Paste / .txt" },
  { key: "youtube", label: "YouTube" },
  { key: "pdf", label: "PDF" },
  { key: "epub", label: "EPUB" },
  { key: "subs", label: "Subtitles" },
  { key: "article", label: "Article URL" },
];

const inputClass =
  "rounded-lg border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors";

function AddBookModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [mode, setMode] = useState<Mode>("paste");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<"paste" | "txt">("paste");
  const [url, setUrl] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfPages, setPdfPages] = useState("");
  const [epubFile, setEpubFile] = useState<File | null>(null);
  const [subsFiles, setSubsFiles] = useState<File[]>([]);
  const [subsResult, setSubsResult] = useState<SubtitleImportResult | null>(null);
  const [topic, setTopic] = useState("");
  const [tags, setTags] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ScoreResult | null>(null);
  const [checking, setChecking] = useState(false);

  const handleTxtFile = async (file: File) => {
    const content = await file.text();
    setText(content);
    setSource("txt");
    setPreview(null);
    if (!title.trim()) setTitle(file.name.replace(/\.txt$/i, ""));
  };

  const checkDifficulty = async () => {
    if (!text.trim()) return;
    setChecking(true);
    setError(null);
    try {
      setPreview(await api.scoreText(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to score text.");
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    setError(null);
    const tagList = tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    if (mode === "paste") {
      if (!title.trim() || !text.trim()) {
        setError("Title and text are both required.");
        return;
      }
      setSubmitting(true);
      try {
        await api.createBook({ title: title.trim(), text, source, topic, tags: tagList });
        onCreated();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add item.");
        setSubmitting(false);
      }
      return;
    }

    if (mode === "youtube" || mode === "article") {
      if (!url.trim()) {
        setError("Paste a URL first.");
        return;
      }
      setSubmitting(true);
      try {
        const body = { url: url.trim(), topic, tags: tagList };
        if (mode === "youtube") await api.importYoutube(body);
        else await api.importArticle(body);
        onCreated();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Import failed.");
        setSubmitting(false);
      }
      return;
    }

    if (mode === "subs") {
      if (subsFiles.length === 0) {
        setError("Choose one or more subtitle files first.");
        return;
      }
      setSubmitting(true);
      setSubsResult(null);
      try {
        const result = await api.importSubtitles({
          files: subsFiles,
          title: title.trim(),
          topic,
          tags,
        });
        // Re-dropping a season is expected to be mostly duplicates, so a batch
        // that wasn't perfectly clean reports per-file rather than closing
        // silently on a partial result.
        if (result.skipped.length === 0 && result.failed.length === 0) {
          onCreated();
          return;
        }
        setSubsResult(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Import failed.");
      }
      setSubmitting(false);
      return;
    }

    if (mode === "epub") {
      if (!epubFile) {
        setError("Choose an EPUB file first.");
        return;
      }
      setSubmitting(true);
      try {
        await api.importEpub({ file: epubFile, title: title.trim(), topic, tags });
        onCreated();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Import failed.");
        setSubmitting(false);
      }
      return;
    }

    // mode === "pdf"
    if (!pdfFile) {
      setError("Choose a PDF file first.");
      return;
    }
    setSubmitting(true);
    try {
      await api.importPdf({
        file: pdfFile,
        title: title.trim(),
        topic,
        tags,
        pages: pdfPages.trim(),
      });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-md bg-surface shadow-xl rounded-t-2xl sm:rounded-2xl p-5 flex flex-col gap-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold font-serif">Add to Library</h2>

        {subsResult && (
          <div className="rounded-lg border border-border bg-paper p-3 text-sm flex flex-col gap-1">
            <p className="font-medium">
              Imported {subsResult.imported.length} of{" "}
              {subsResult.imported.length +
                subsResult.skipped.length +
                subsResult.failed.length}
            </p>
            {subsResult.skipped.length > 0 && (
              <p className="text-muted text-xs">
                {subsResult.skipped.length} already in the Library:{" "}
                {subsResult.skipped.map((s) => s.filename).join(", ")}
              </p>
            )}
            {subsResult.failed.map((f) => (
              <p key={f.filename} className="text-danger text-xs">
                {f.filename}: {f.error}
              </p>
            ))}
          </div>
        )}

        <div className="flex gap-1 rounded-lg bg-paper p-1 text-sm">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => {
                setMode(m.key);
                setError(null);
              }}
              className={`flex-1 rounded-md px-2 py-1.5 transition-colors ${
                mode === m.key
                  ? "bg-surface shadow-sm text-ink font-medium"
                  : "text-muted hover:text-ink"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {mode === "paste" && (
          <>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
              className={inputClass}
            />
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setSource("paste");
                setPreview(null);
              }}
              placeholder="Paste Korean text here…"
              rows={8}
              className={`${inputClass} resize-none`}
            />
            <label className="text-sm text-muted flex flex-col gap-1">
              or upload a .txt file
              <input
                type="file"
                accept=".txt"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleTxtFile(file);
                }}
                className="text-sm"
              />
            </label>
            <div className="flex items-center gap-3 text-sm">
              <button
                onClick={checkDifficulty}
                disabled={checking || !text.trim()}
                className="text-muted hover:text-ink transition-colors disabled:opacity-50"
              >
                {checking ? "Checking…" : "Check difficulty"}
              </button>
              {preview && (
                <span className="text-muted">
                  {preview.coverage !== null && (
                    <span className={coverageClass(preview.coverage)}>
                      {Math.round(preview.coverage * 100)}% known
                    </span>
                  )}
                  {preview.coverage !== null && " · "}
                  {preview.new_per_page} new/pg
                  {preview.general_level !== null && preview.general_coverage !== null && (
                    <>
                      {" · general: "}
                      {preview.general_level} ({Math.round(preview.general_coverage * 100)}%)
                    </>
                  )}
                </span>
              )}
            </div>
          </>
        )}

        {(mode === "youtube" || mode === "article") && (
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={mode === "youtube" ? "https://youtube.com/watch?v=…" : "https://example.com/article"}
            className={inputClass}
          />
        )}

        {mode === "pdf" && (
          <>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title (defaults to filename)"
              className={inputClass}
            />
            <label className="text-sm text-muted flex flex-col gap-1">
              PDF file
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </label>
            <input
              value={pdfPages}
              onChange={(e) => setPdfPages(e.target.value)}
              placeholder="Page range, e.g. 1-20 (optional)"
              className={inputClass}
            />
          </>
        )}

        {mode === "epub" && (
          <>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title (defaults to filename)"
              className={inputClass}
            />
            <label className="text-sm text-muted flex flex-col gap-1">
              EPUB file
              <input
                type="file"
                accept=".epub,application/epub+zip"
                onChange={(e) => setEpubFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </label>
          </>
        )}

        {mode === "subs" && (
          <>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title (single file only — a batch titles per filename)"
              className={inputClass}
            />
            <label className="text-sm text-muted flex flex-col gap-1">
              Subtitle files — .srt, .vtt, .smi, .ass, .ttml
              <input
                type="file"
                multiple
                accept=".srt,.vtt,.webvtt,.smi,.sami,.ass,.ssa,.ttml,.dfxp,.xml"
                onChange={(e) => {
                  setSubsFiles(Array.from(e.target.files ?? []));
                  setSubsResult(null);
                }}
                className="text-sm"
              />
            </label>
            {subsFiles.length > 0 && (
              <p className="text-xs text-muted -mt-1">
                {subsFiles.length} file{subsFiles.length === 1 ? "" : "s"} selected — one
                item each, imported in filename order.
              </p>
            )}
          </>
        )}

        {mode !== "paste" && (
          <p className="text-xs text-muted -mt-1">
            {mode === "pdf" || mode === "epub" || mode === "subs"
              ? "Duplicate files (same file re-uploaded) are detected automatically."
              : "Re-importing the same link won't create a duplicate item."}
          </p>
        )}

        <div className="flex gap-2">
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="rounded-lg border border-border bg-transparent px-2 py-2 text-sm flex-1"
          >
            <option value="">No topic</option>
            {TOPICS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="tags, comma, separated"
            className={`${inputClass} flex-1`}
          />
        </div>

        {error && <p className="text-danger text-sm">{error}</p>}

        <div className="flex gap-2 justify-end mt-2">
          <button
            // A partial batch leaves the modal open on its summary, so closing
            // still has to refresh the Library for whatever did import.
            onClick={subsResult?.imported.length ? onCreated : onClose}
            className="px-4 py-2 text-sm rounded-full border border-border hover:bg-paper transition-colors"
          >
            {subsResult ? "Close" : "Cancel"}
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-4 py-2 text-sm rounded-full bg-accent text-accent-ink shadow-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
      </div>
    </div>
  );
}
