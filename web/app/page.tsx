"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Book, type ScoreResult } from "@/lib/api";

type Sort = "recent" | "easiest";

// Coverage bands from docs/NEXT_STAGE_OPTIONS.md: ~0.95+ comfortable, 0.90-0.95
// productive study zone, <0.85 a slog. Colour the % so difficulty reads at a glance.
function coverageClass(coverage: number): string {
  if (coverage >= 0.95) return "text-accent";
  if (coverage < 0.85) return "text-danger";
  return "text-ink";
}

function ScoreLine({ book }: { book: Book }) {
  if (!book.scored_at) return null;
  return (
    <span className="text-xs text-muted">
      {book.coverage !== null && (
        <span className={coverageClass(book.coverage)}>
          {Math.round(book.coverage * 100)}% known
        </span>
      )}
      {book.coverage !== null && book.new_per_page !== null && " · "}
      {book.new_per_page !== null && `${book.new_per_page} new/pg`}
    </span>
  );
}

export default function HomePage() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [sort, setSort] = useState<Sort>("recent");
  const [scoring, setScoring] = useState<number | null>(null);

  const refresh = () => {
    api
      .listBooks()
      .then(setBooks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load books."));
  };

  useEffect(refresh, []);

  const score = async (id: number) => {
    setScoring(id);
    try {
      const updated = await api.scoreBook(id);
      setBooks((prev) => prev?.map((b) => (b.id === id ? updated : b)) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to score book.");
    } finally {
      setScoring(null);
    }
  };

  // "Easiest unread" sorts by new-words-per-page ascending; unscored books sink
  // to the bottom (unknown difficulty). "recent" keeps the API's id order reversed.
  const displayed = books ? [...books] : books;
  if (displayed) {
    if (sort === "easiest") {
      displayed.sort((a, b) => {
        const av = a.new_per_page ?? Infinity;
        const bv = b.new_per_page ?? Infinity;
        return av - bv;
      });
    } else {
      displayed.sort((a, b) => b.id - a.id);
    }
  }

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold font-serif">Korean Reader</h1>
        <div className="flex items-center gap-3">
          <Link href="/terms" className="text-sm text-muted hover:text-ink transition-colors">
            Terms
          </Link>
          <Link href="/settings" className="text-sm text-muted hover:text-ink transition-colors">
            Settings
          </Link>
          <button
            onClick={() => setModalOpen(true)}
            className="rounded-full bg-accent text-accent-ink px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 transition-opacity"
          >
            + Add book
          </button>
        </div>
      </div>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}

      {books === null && !error && <p className="text-muted">Loading…</p>}

      {books?.length === 0 && (
        <p className="text-muted">No books yet. Add one to get started.</p>
      )}

      {books && books.length > 0 && (
        <div className="flex items-center gap-2 mb-3 text-sm">
          <span className="text-muted">Sort:</span>
          <button
            onClick={() => setSort("recent")}
            className={sort === "recent" ? "text-ink font-medium" : "text-muted hover:text-ink"}
          >
            Recent
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
        {displayed?.map((book) => (
          <li
            key={book.id}
            className="rounded-xl border border-border bg-surface p-4 shadow-sm"
          >
            <Link
              href={`/read/?id=${book.id}`}
              className="block hover:text-accent transition-colors"
            >
              <div className="font-medium">{book.title}</div>
              <div className="text-sm text-muted">
                {book.current_page} / {book.page_count} pages
              </div>
            </Link>
            <div className="mt-2 flex items-center gap-3">
              <ScoreLine book={book} />
              <button
                onClick={() => score(book.id)}
                disabled={scoring === book.id}
                className="text-xs text-muted hover:text-ink transition-colors disabled:opacity-50"
              >
                {scoring === book.id
                  ? "Scoring…"
                  : book.scored_at
                    ? "re-score"
                    : "Score difficulty"}
              </button>
            </div>
          </li>
        ))}
      </ul>

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

function AddBookModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<"paste" | "txt">("paste");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ScoreResult | null>(null);
  const [checking, setChecking] = useState(false);

  const handleFile = async (file: File) => {
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
    if (!title.trim() || !text.trim()) {
      setError("Title and text are both required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createBook({ title: title.trim(), text, source });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create book.");
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
        <h2 className="text-lg font-semibold font-serif">Add a book</h2>

        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title"
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
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
          className="rounded-lg border border-border bg-transparent px-3 py-2 text-sm resize-none placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
        />

        <label className="text-sm text-muted flex flex-col gap-1">
          or upload a .txt file
          <input
            type="file"
            accept=".txt"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
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
            </span>
          )}
        </div>

        {error && <p className="text-danger text-sm">{error}</p>}

        <div className="flex gap-2 justify-end mt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-full border border-border hover:bg-paper transition-colors"
          >
            Cancel
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
