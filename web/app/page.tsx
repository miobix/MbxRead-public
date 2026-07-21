"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Book } from "@/lib/api";

export default function HomePage() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = () => {
    api
      .listBooks()
      .then(setBooks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load books."));
  };

  useEffect(refresh, []);

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

      <ul className="flex flex-col gap-3">
        {books?.map((book) => (
          <li key={book.id}>
            <Link
              href={`/read/?id=${book.id}`}
              className="block rounded-xl border border-border bg-surface p-4 shadow-sm hover:border-accent transition-colors"
            >
              <div className="font-medium">{book.title}</div>
              <div className="text-sm text-muted">
                {book.current_page} / {book.page_count} pages
              </div>
            </Link>
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

  const handleFile = async (file: File) => {
    const content = await file.text();
    setText(content);
    setSource("txt");
    if (!title.trim()) setTitle(file.name.replace(/\.txt$/i, ""));
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
